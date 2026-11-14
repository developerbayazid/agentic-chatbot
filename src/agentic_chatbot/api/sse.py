"""Map ``TurnEvent`` to Server-Sent Events.

The service already emits a transport-neutral contract, so this module only
renames events and serialises payloads — it never generates or splits text.
``approval_token`` is stripped: it is a graph-internal value that binds a
decision to a proposal, and the client is given a signed ``approval_id``
instead.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from agentic_chatbot.models import TurnEvent

MEDIA_TYPE = "text/event-stream"

EVENT_NAMES = {
    "token": "token",
    "tool_call": "tool_start",
    "tool_result": "tool_end",
    "interrupt": "approval_required",
    "done": "final",
}

SENSITIVE_PAYLOAD_KEYS = {"approval_token"}


def frame(event: str, data: dict) -> str:
    """One SSE frame. ``default=str`` keeps an exotic value from breaking it."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def sanitise(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}

    return {
        key: value
        for key, value in payload.items()
        if key not in SENSITIVE_PAYLOAD_KEYS
    }


def to_frame(
    event: TurnEvent,
    thread_id: str,
    approval_id: str | None = None,
) -> str | None:
    """Translate one service event, or ``None`` if it must not be sent."""
    name = EVENT_NAMES.get(event.type)

    if name is None:
        return None

    if event.type == "token":
        return frame(name, {"content": event.content})

    if event.type == "tool_call":
        arguments = event.content
        try:
            arguments = json.loads(event.content)
        except (TypeError, ValueError):
            pass

        return frame(
            name,
            {
                "tool": event.name,
                "arguments": arguments,
                "tool_call_id": event.call_id,
            },
        )

    if event.type == "tool_result":
        return frame(
            name,
            {
                "tool": event.name,
                "result": event.content,
                "tool_call_id": event.call_id,
            },
        )

    if event.type == "interrupt":
        payload = sanitise(event.payload)
        return frame(
            name,
            {
                "approval_id": approval_id,
                "thread_id": thread_id,
                "action": payload.get("tool"),
                "title": payload.get("title"),
                "arguments": payload.get("arguments") or {},
                "details": payload.get("details") or [],
                "warnings": payload.get("warnings") or [],
                "allowed_decisions": ["approve", "edit", "reject"],
            },
        )

    return frame(name, {"title": event.title})


def start_frames(thread_id: str) -> Iterator[str]:
    yield frame("thread", {"thread_id": thread_id})
    yield frame("status", {"status": "processing"})
