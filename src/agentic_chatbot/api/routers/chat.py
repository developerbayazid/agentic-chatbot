"""Chat endpoints.

The router orchestrates; it does not talk to a model. Everything happens in
``ChatService.stream_turn`` — the same generator the CLI drives — and the router
only collects its events, decides the HTTP result, and returns.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from agentic_chatbot.api.dependencies import (
    ChatServiceDep,
    ContainerDep,
    CurrentUserDep,
    SettingsDep,
    ThreadServiceDep,
)
from agentic_chatbot.api.errors import APIError
from agentic_chatbot.api.schemas import ChatRequest, ChatResponse
from agentic_chatbot.api.security import make_approval_id
from agentic_chatbot.api.sse import MEDIA_TYPE, frame, start_frames, to_frame

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@dataclass
class TurnOutcome:
    """What a completed turn produced, without any transport concept."""

    response: str
    title: str | None
    approval: dict | None


def resolve_thread(
    threads: ThreadServiceDep, subject: str, thread_id: str | None
):
    """Return an owned thread ID, creating one when the caller supplied none."""
    if thread_id is None:
        return threads.create_thread(owner_id=subject).thread_id

    owned = threads.get_thread(thread_id)

    if owned is None or owned.owner_id != subject:
        raise APIError(
            "THREAD_NOT_FOUND",
            "The requested conversation was not found.",
            status.HTTP_404_NOT_FOUND,
        )

    return thread_id


def ensure_no_pending_approval(chat_service, thread_id: str, subject: str) -> None:
    """Refuse a new message while a previous action is still awaiting a human.

    The graph would otherwise be asked to continue with an unanswered tool call,
    which the model provider rejects. The CLI guards this identically.
    """
    if chat_service.get_pending_interrupt(thread_id, owner_id=subject) is None:
        return

    raise APIError(
        "APPROVAL_PENDING",
        "A previous action is awaiting approval. Decide it before sending "
        "another message.",
        status.HTTP_409_CONFLICT,
    )


def run_turn(
    chat_service,
    thread_id: str,
    message: str,
    subject: str,
) -> TurnOutcome:
    """Drive one turn and collect its events.

    ``stream_turn`` streams genuine provider chunks, so the tokens collected here
    are exactly what a client would receive over SSE.
    """
    chunks: list[str] = []
    title: str | None = None
    approval: dict | None = None

    for event in chat_service.stream_turn(thread_id, message, owner_id=subject):
        if event.type == "token":
            chunks.append(event.content)
        elif event.type == "interrupt":
            approval = event.payload or {}
        elif event.type == "done":
            title = event.title

    return TurnOutcome(
        response="".join(chunks).strip(),
        title=title,
        approval=approval,
    )


def approval_id_for(settings, subject: str, thread_id: str, payload: dict) -> str:
    return make_approval_id(
        settings,
        subject,
        thread_id,
        payload.get("interrupt_id"),
        payload.get("approval_token", ""),
    )


@router.post("", response_model=ChatResponse)
def send_message(
    body: ChatRequest,
    user: CurrentUserDep,
    threads: ThreadServiceDep,
    chat_service: ChatServiceDep,
    container: ContainerDep,
    settings: SettingsDep,
) -> ChatResponse:
    thread_id = resolve_thread(threads, user.subject, body.thread_id)
    ensure_no_pending_approval(chat_service, thread_id, user.subject)

    # One conversation is driven by one turn at a time. Different conversations
    # still run concurrently; this only prevents a double-driven graph.
    with container.thread_lock(thread_id):
        outcome = run_turn(chat_service, thread_id, body.message, user.subject)

    if outcome.approval is not None:
        return ChatResponse(
            thread_id=thread_id,
            response=outcome.response,
            status="awaiting_approval",
            approval_id=approval_id_for(
                settings, user.subject, thread_id, outcome.approval
            ),
        )

    return ChatResponse(
        thread_id=thread_id,
        response=outcome.response,
        status="completed",
        title=outcome.title,
    )


def _event_stream(
    chat_service,
    container,
    settings,
    thread_id: str,
    message: str,
    subject: str,
) -> Iterator[str]:
    """Yield SSE frames for one turn.

    The generator holds the per-thread lock for its whole life and releases it in
    ``finally``, so a client disconnect (which raises ``GeneratorExit``) closes
    the graph stream instead of leaking it.
    """
    lock = container.thread_lock(thread_id)

    if not lock.acquire(blocking=False):
        yield frame(
            "error",
            {"code": "THREAD_BUSY", "message": "This conversation is busy."},
        )
        return

    try:
        # Deliberately a loop rather than `yield from`: this generator converts
        # destructive GeneratorExit into a clean close (below), and `yield from`
        # would let the sub-generator own that protocol instead of this frame.
        for opening in start_frames(thread_id):  # noqa: UP028
            yield opening

        for event in chat_service.stream_turn(thread_id, message, owner_id=subject):
            approval_id = None

            if event.type == "interrupt":
                approval_id = approval_id_for(
                    settings, subject, thread_id, event.payload or {}
                )

            outgoing = to_frame(event, thread_id, approval_id)

            if outgoing is not None:
                yield outgoing
    except GeneratorExit:
        logger.debug("streaming client disconnected on thread %s", thread_id)
        raise
    except Exception:  # noqa: BLE001 - reported as a frame, logged in full
        logger.exception("streaming turn failed on thread %s", thread_id)
        yield frame(
            "error",
            {"code": "STREAM_ERROR", "message": "The response failed."},
        )
    finally:
        lock.release()


@router.post("/stream")
def stream_message(
    body: ChatRequest,
    user: CurrentUserDep,
    threads: ThreadServiceDep,
    chat_service: ChatServiceDep,
    container: ContainerDep,
    settings: SettingsDep,
) -> StreamingResponse:
    thread_id = resolve_thread(threads, user.subject, body.thread_id)
    ensure_no_pending_approval(chat_service, thread_id, user.subject)

    return StreamingResponse(
        _event_stream(
            chat_service,
            container,
            settings,
            thread_id,
            body.message,
            user.subject,
        ),
        media_type=MEDIA_TYPE,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
