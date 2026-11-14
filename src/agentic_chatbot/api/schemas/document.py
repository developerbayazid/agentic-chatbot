"""Document schemas.

``source`` is deliberately absent: it is a path on the server and is never
returned to API consumers.
"""

from __future__ import annotations

from pydantic import Field

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


class DocumentSearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=4_000)
    namespace: str | None = Field(default=None, max_length=64)
    k: int = Field(default=4, ge=1, le=10)
