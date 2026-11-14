"""Thread endpoints.

Every lookup is scoped to the authenticated subject. A thread that exists but
belongs to someone else answers 404, not 403: otherwise the response confirms
that an ID exists, which is exactly what an attacker wants to learn.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agentic_chatbot.api.dependencies import (
    ChatServiceDep,
    CurrentUserDep,
    ThreadServiceDep,
)
from agentic_chatbot.api.errors import APIError
from agentic_chatbot.api.schemas import (
    ThreadHistoryResponse,
    ThreadListResponse,
    ThreadMessage,
    ThreadResponse,
    ThreadUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/threads", tags=["threads"])


def _not_found() -> APIError:
    return APIError(
        "THREAD_NOT_FOUND",
        "The requested conversation was not found.",
        status.HTTP_404_NOT_FOUND,
    )


def owned_thread(service, thread_id: str, subject: str):
    """Return the thread, or raise 404 unless ``subject`` owns it."""
    thread = service.get_thread(thread_id)

    if thread is None or thread.owner_id != subject:
        raise _not_found()

    return thread


def _to_response(thread) -> ThreadResponse:
    return ThreadResponse(
        thread_id=thread.thread_id,
        title=thread.title,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.get("", response_model=ThreadListResponse)
def list_threads(
    user: CurrentUserDep, service: ThreadServiceDep
) -> ThreadListResponse:
    threads = service.list_threads(owner_id=user.subject)

    return ThreadListResponse(
        threads=[_to_response(thread) for thread in threads]
    )


@router.get("/{thread_id}", response_model=ThreadResponse)
def get_thread(
    thread_id: str, user: CurrentUserDep, service: ThreadServiceDep
) -> ThreadResponse:
    return _to_response(owned_thread(service, thread_id, user.subject))


@router.patch("/{thread_id}", response_model=ThreadResponse)
def rename_thread(
    thread_id: str,
    body: ThreadUpdateRequest,
    user: CurrentUserDep,
    service: ThreadServiceDep,
) -> ThreadResponse:
    owned_thread(service, thread_id, user.subject)

    service.rename_thread(thread_id, body.title)

    return _to_response(service.get_thread(thread_id))


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_thread(
    thread_id: str, user: CurrentUserDep, service: ThreadServiceDep
) -> None:
    owned_thread(service, thread_id, user.subject)

    # ThreadService removes the LangGraph checkpoints and then the metadata, so
    # deleting a conversation cannot leave orphaned message state behind.
    if not service.delete_thread(thread_id):
        raise _not_found()


@router.get("/{thread_id}/history", response_model=ThreadHistoryResponse)
def get_history(
    thread_id: str,
    user: CurrentUserDep,
    service: ThreadServiceDep,
    chat_service: ChatServiceDep,
) -> ThreadHistoryResponse:
    owned_thread(service, thread_id, user.subject)

    messages: list[ThreadMessage] = []

    for message in chat_service.get_messages(thread_id):
        if isinstance(message, HumanMessage):
            messages.append(ThreadMessage(role="user", content=str(message.content)))
        elif isinstance(message, AIMessage):
            if message.content:
                messages.append(
                    ThreadMessage(role="assistant", content=str(message.content))
                )
        elif isinstance(message, ToolMessage):
            # Summarised, never the raw internal state.
            messages.append(
                ThreadMessage(
                    role="tool",
                    content=f"{message.name or 'tool'}: {str(message.content)[:500]}",
                )
            )
        else:
            logger.debug("skipping a non-conversational message in history")

    return ThreadHistoryResponse(thread_id=thread_id, messages=messages)
