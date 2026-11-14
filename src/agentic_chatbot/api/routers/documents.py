"""Document endpoints.

Uploads land in a per-user namespace and are owned by the caller. Responses
never include ``source``, which is a server path.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, UploadFile, status

from agentic_chatbot.api.dependencies import (
    ContainerDep,
    CurrentUserDep,
    DocumentServiceDep,
)
from agentic_chatbot.api.errors import APIError
from agentic_chatbot.api.schemas import (
    DocumentListResponse,
    DocumentResponse,
    IngestResponse,
)
from agentic_chatbot.api.uploads import UploadError, store_upload
from agentic_chatbot.loaders import PDF_SUFFIXES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def namespace_for(subject: str) -> str:
    """A deterministic per-user namespace.

    The schema's ``UNIQUE (namespace, source)`` would otherwise let one user's
    upload collide with another's, and retrieval already scopes by owner.
    """
    return f"u_{subject}"


def _to_response(document) -> DocumentResponse:
    return DocumentResponse(
        doc_id=document.doc_id,
        title=document.title,
        namespace=document.namespace,
        size_bytes=document.size_bytes,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get("", response_model=DocumentListResponse)
def list_documents(
    user: CurrentUserDep, service: DocumentServiceDep
) -> DocumentListResponse:
    documents = service.list_documents(owner_id=user.subject)

    return DocumentListResponse(
        documents=[_to_response(document) for document in documents],
        namespaces=service.list_namespaces(owner_id=user.subject),
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(
    doc_id: str, user: CurrentUserDep, service: DocumentServiceDep
) -> DocumentResponse:
    document = service.get_document(doc_id)

    if document is None or document.owner_id != user.subject:
        raise APIError(
            "DOCUMENT_NOT_FOUND",
            "The requested document was not found.",
            status.HTTP_404_NOT_FOUND,
        )

    return _to_response(document)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: str, user: CurrentUserDep, service: DocumentServiceDep
) -> None:
    document = service.get_document(doc_id)

    if document is None or document.owner_id != user.subject:
        raise APIError(
            "DOCUMENT_NOT_FOUND",
            "The requested document was not found.",
            status.HTTP_404_NOT_FOUND,
        )

    # The service also prunes the document's FAISS entries and invalidates the
    # namespace's BM25 cache, so search cannot return a deleted chunk.
    service.delete_document(doc_id)


@router.post("", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    user: CurrentUserDep,
    container: ContainerDep,
    file: UploadFile = File(...),
) -> IngestResponse:
    settings = container.settings
    suffix = (file.filename or "").lower().rsplit(".", 1)[-1]
    limit = (
        settings.rag_max_pdf_bytes
        if f".{suffix}" in PDF_SUFFIXES
        else settings.rag_max_text_bytes
    )
    limit = min(limit, settings.api_max_upload_bytes)

    def read_chunk() -> bytes:
        return file.file.read(64 * 1024)

    try:
        stored = store_upload(
            container=container,
            subject=user.subject,
            namespace=namespace_for(user.subject),
            filename=file.filename,
            read_chunk=read_chunk,
            max_bytes=limit,
        )
    except UploadError as error:
        raise APIError(error.code, error.message, error.status_code) from error
    finally:
        file.file.close()

    document = container.document_service.find_document(
        namespace_for(user.subject), stored.path
    )

    if document is None:  # pragma: no cover - ingest_file raises instead
        raise APIError(
            "INGEST_FAILED",
            "The document could not be indexed.",
            422,
        )

    return IngestResponse(
        document=_to_response(document),
        chunks_created=stored.chunks_created,
        skipped=stored.skipped,
    )
