"""Thread schemas."""

from __future__ import annotations

from pydantic import Field

from agentic_chatbot.api.schemas.auth import StrictModel


class ThreadResponse(StrictModel):
    thread_id: str
    title: str
    created_at: str | None = None
    updated_at: str | None = None


class ThreadListResponse(StrictModel):
    threads: list[ThreadResponse]


class ThreadUpdateRequest(StrictModel):
    title: str = Field(min_length=1, max_length=100)


class ThreadMessage(StrictModel):
    role: str
    content: str


class ThreadHistoryResponse(StrictModel):
    thread_id: str
    messages: list[ThreadMessage]
