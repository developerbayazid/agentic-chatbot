"""Approval schemas.

``respond`` is intentionally absent from ``DecisionRequest``: the graph's
approval node implements approve/edit/reject only, and mapping a free-text
response onto a rejection would silently change what the human decided.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from agentic_chatbot.api.schemas.auth import StrictModel

Decision = Literal["approve", "edit", "reject"]
ALLOWED_DECISIONS: list[str] = ["approve", "edit", "reject"]


class ApprovalSummary(StrictModel):
    approval_id: str
    thread_id: str
    action: str
    title: str
    arguments: dict[str, Any]
    allowed_decisions: list[str]


class ApprovalDetail(ApprovalSummary):
    tool_call_id: str | None = None
    editable_fields: list[str] = []
    field_types: dict[str, str] = {}
    details: list[Any] = []
    warnings: list[Any] = []
    requested_by: str | None = None
    reason: str | None = None


class DecisionRequest(StrictModel):
    decision: Decision
    edited_arguments: dict[str, Any] | None = None
    comment: str | None = Field(default=None, max_length=2_000)


class DecisionResponse(StrictModel):
    approval_id: str
    status: Literal["completed", "awaiting_approval"]
    response: str = ""
    thread_id: str
    title: str | None = None
    next_approval_id: str | None = None
