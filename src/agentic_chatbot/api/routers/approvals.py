"""Human-in-the-loop approvals.

There is no second approval system here: this router reads the same LangGraph
interrupts the CLI does and resumes the same graph through ``ChatService``.

The security model rests on one rule — **the client never supplies anything the
server can derive.** An ``approval_id`` is an HMAC over the subject, the thread,
the live interrupt id, and the graph's own approval token. To act, a request
must prove it belongs to the caller's *currently pending* interrupt:

1. the handle is well formed,
2. it names an interrupt among the caller's own threads (so ownership and
   authorization are the same check),
3. no other thread is waiting on it.

The decision is then made under the per-thread lock, after re-reading the live
interrupt, so a stale, replayed, or concurrent decision cannot execute a tool.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, status

from agentic_chatbot.api.dependencies import (
    ChatServiceDep,
    ContainerDep,
    CurrentUserDep,
    SettingsDep,
    ThreadServiceDep,
)
from agentic_chatbot.api.errors import APIError
from agentic_chatbot.api.routers.chat import TurnOutcome
from agentic_chatbot.api.schemas import (
    ApprovalDetail,
    ApprovalSummary,
    DecisionRequest,
    DecisionResponse,
)
from agentic_chatbot.api.security import (
    ApprovalHandleError,
    handle_for,
    parse_approval_id,
    verify_handle,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])

_ALLOWED_DECISIONS = ["approve", "edit", "reject"]


def _invalid() -> APIError:
    return APIError(
        "APPROVAL_INVALID",
        "This approval id is not valid.",
        status.HTTP_400_BAD_REQUEST,
    )


def _not_found() -> APIError:
    return APIError(
        "APPROVAL_NOT_FOUND",
        "No pending approval matches this request.",
        status.HTTP_404_NOT_FOUND,
    )


def _stale() -> APIError:
    return APIError(
        "APPROVAL_STALE",
        "This approval no longer matches the pending action.",
        status.HTTP_409_CONFLICT,
    )


def _not_pending() -> APIError:
    return APIError(
        "APPROVAL_NOT_PENDING",
        "There is no pending approval for this conversation.",
        status.HTTP_409_CONFLICT,
    )


def _summary(handle: str, thread_id: str, payload: dict) -> ApprovalSummary:
    return ApprovalSummary(
        approval_id=handle,
        thread_id=thread_id,
        action=str(payload.get("tool") or "unknown"),
        title=str(payload.get("title") or payload.get("tool") or "Approval"),
        arguments=payload.get("arguments") or {},
        allowed_decisions=list(_ALLOWED_DECISIONS),
    )


def find_pending(threads, chat_service, settings, subject, approval_id=None):
    """Return ``(handle, thread_id, pending, payload)`` for the caller's interrupts.

    ``approval_id`` narrows the search to at most one entry. Because the list is
    restricted to threads the caller owns, a handle naming somebody else's
    conversation simply matches nothing — authorization is not a separate,
    forgettable check.
    """
    found = []

    for thread in threads.list_threads(owner_id=subject):
        pending = chat_service.get_pending_interrupt(
            thread.thread_id, owner_id=subject
        )

        if not pending:
            continue

        payload = pending.get("value")

        if not isinstance(payload, dict):
            continue

        handle = handle_for(settings, subject, thread.thread_id, pending)

        if handle is None:
            continue

        if approval_id is not None and handle != approval_id:
            continue

        found.append((handle, thread.thread_id, pending, payload))

        if approval_id is not None:
            break

    return found


@router.get("", response_model=list[ApprovalSummary])
def list_approvals(
    user: CurrentUserDep,
    threads: ThreadServiceDep,
    chat_service: ChatServiceDep,
    settings: SettingsDep,
) -> list[ApprovalSummary]:
    return [
        _summary(handle, thread_id, payload)
        for handle, thread_id, _, payload in find_pending(
            threads, chat_service, settings, user.subject
        )
    ]


@router.get("/{approval_id}", response_model=ApprovalDetail)
def get_approval(
    approval_id: str,
    user: CurrentUserDep,
    threads: ThreadServiceDep,
    chat_service: ChatServiceDep,
    settings: SettingsDep,
) -> ApprovalDetail:
    try:
        parse_approval_id(approval_id)
    except ApprovalHandleError as error:
        raise _invalid() from error

    found = find_pending(
        threads, chat_service, settings, user.subject, approval_id
    )

    if not found:
        raise _not_found()

    handle, thread_id, _, payload = found[0]

    return ApprovalDetail(
        **_summary(handle, thread_id, payload).model_dump(),
        tool_call_id=payload.get("tool_call_id"),
        editable_fields=list(payload.get("editable_fields") or []),
        field_types=dict(payload.get("field_types") or {}),
        details=list(payload.get("details") or []),
        warnings=list(payload.get("warnings") or []),
        requested_by=payload.get("requested_by"),
        reason=payload.get("reason"),
    )


def _resume_payload(body: DecisionRequest, approval_token: str) -> dict[str, Any]:
    """Translate the API vocabulary into the graph's decision shape.

    ``approval_token`` comes from the live interrupt, never from the client, so a
    decision can only ever apply to the proposal the server just verified.
    """
    if body.decision == "edit" and body.edited_arguments is None:
        raise APIError(
            "INVALID_DECISION",
            "An edited decision must include edited_arguments.",
            422,
        )

    if body.decision != "edit" and body.edited_arguments is not None:
        raise APIError(
            "INVALID_DECISION",
            "edited_arguments is only valid for an edit decision.",
            422,
        )

    payload: dict[str, Any] = {
        "action": body.decision,
        "approval_token": approval_token,
        "comment": body.comment or "",
    }

    if body.decision == "edit":
        payload["arguments"] = body.edited_arguments

    return payload


def _resume(chat_service, thread_id: str, decision: dict, subject: str) -> TurnOutcome:
    """Resume the graph, collecting events exactly as a normal turn does."""
    chunks: list[str] = []
    title: str | None = None

    for event in chat_service.resume_turn(thread_id, decision, owner_id=subject):
        if event.type == "token":
            chunks.append(event.content)
        elif event.type == "done":
            title = event.title

    return TurnOutcome(
        response="".join(chunks).strip(), title=title, approval=None
    )


@router.post("/{approval_id}/decision", response_model=DecisionResponse)
def decide(
    approval_id: str,
    body: DecisionRequest,
    user: CurrentUserDep,
    threads: ThreadServiceDep,
    chat_service: ChatServiceDep,
    container: ContainerDep,
    settings: SettingsDep,
) -> DecisionResponse:
    try:
        parse_approval_id(approval_id)
    except ApprovalHandleError as error:
        raise _invalid() from error

    found = find_pending(
        threads, chat_service, settings, user.subject, approval_id
    )

    if not found:
        # Either already decided (a duplicate or a concurrent double-submit) or
        # never the caller's. Neither may execute anything.
        raise _not_pending()

    handle, thread_id, pending, payload = found[0]

    try:
        verify_handle(settings, user.subject, thread_id, pending, approval_id)
    except ApprovalHandleError as error:
        raise _stale() from error

    decision = _resume_payload(body, payload.get("approval_token", ""))

    with container.thread_lock(thread_id):
        # Re-read under the lock: the first decision wins and the rest see 409.
        live = chat_service.get_pending_interrupt(
            thread_id, owner_id=user.subject
        )

        if not live:
            raise _not_pending()

        try:
            verify_handle(settings, user.subject, thread_id, live, approval_id)
        except ApprovalHandleError as error:
            raise _stale() from error

        outcome = _resume(chat_service, thread_id, decision, user.subject)

    following = handle_for(
        settings,
        user.subject,
        thread_id,
        chat_service.get_pending_interrupt(thread_id, owner_id=user.subject),
    )

    return DecisionResponse(
        approval_id=handle,
        thread_id=thread_id,
        status="awaiting_approval" if following else "completed",
        response=outcome.response,
        title=outcome.title,
        next_approval_id=following,
    )
