"""Domain models shared across services and the CLI."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Thread:
    thread_id: str
    title: str
    created_at: str | None
    updated_at: str | None


@dataclass(frozen=True)
class Note:
    note_id: str
    thread_id: str
    title: str
    content: str
    created_at: str | None


@dataclass(frozen=True)
class Chunk:
    content: str
    page: int | None = None


@dataclass(frozen=True)
class Document:
    doc_id: str
    namespace: str
    source: str
    title: str
    content_hash: str
    size_bytes: int
    created_at: str | None
    updated_at: str | None


@dataclass(frozen=True)
class DocumentHit:
    chunk_id: str
    doc_id: str
    namespace: str
    title: str
    source: str
    chunk_index: int
    page: int | None
    content: str
    score: float
    vector_score: float | None = None
    bm25_score: float | None = None


@dataclass(frozen=True)
class TurnEvent:
    """A single event emitted while processing one conversation turn."""

    type: Literal["token", "tool_call", "tool_result", "interrupt", "done"]
    content: str = ""
    title: str | None = None
    name: str | None = None
    payload: dict | None = None
