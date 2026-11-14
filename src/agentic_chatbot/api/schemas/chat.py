"""Conversation schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from agentic_chatbot.api.schemas.auth import StrictModel


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=32_000)
    thread_id: str | None = Field(default=None, max_length=128)

    @field_validator("thread_id", mode="before")
    @classmethod
    def _blank_means_new_conversation(cls, value: object) -> object:
        """Treat ``""`` and whitespace as "start a new conversation".

        A form or client that has no thread yet sends an empty field; rejecting
        that as malformed makes the most obvious request fail.
        """
        if isinstance(value, str) and not value.strip():
            return None

        return value

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")

        return value


class ChatResponse(StrictModel):
    thread_id: str
    response: str
    status: Literal["completed", "awaiting_approval"]
    title: str | None = None
    approval_id: str | None = None
