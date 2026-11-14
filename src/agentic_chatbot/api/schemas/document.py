"""Document schemas.

``source`` is deliberately absent: it is a path on the server and is never
returned to API consumers.
"""

from __future__ import annotations

from agentic_chatbot.api.schemas.auth import StrictModel


class DocumentResponse(StrictModel):
    doc_id: str
    title: str
    namespace: str
    size_bytes: int
    created_at: str | None = None
    updated_at: str | None = None


class DocumentListResponse(StrictModel):
    documents: list[DocumentResponse]
    namespaces: list[str]


class IngestResponse(StrictModel):
    document: DocumentResponse
    chunks_created: int
    skipped: bool
    warning: str | None = None
