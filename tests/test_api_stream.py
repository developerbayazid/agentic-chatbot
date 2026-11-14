"""SSE streaming: frame format, every event type, and disconnect safety."""

from __future__ import annotations

import json
import threading

import pytest

from agentic_chatbot.api.sse import frame, sanitise, to_frame
from agentic_chatbot.models import TurnEvent
from tests.test_api_chat import ScriptedChatService


def parse(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into ``(event, data)`` pairs."""
    events = []

    for block in body.split("\n\n"):
        lines = [line for line in block.splitlines() if line.strip()]
        name = None
        data = None

        for line in lines:
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])

        if name is not None:
            events.append((name, data))

    return events


@pytest.fixture
def streamed(api_client):
    container = api_client.app.state.container
    original = container.chat_service

    def install(events=None, error=None):
        double = ScriptedChatService(events=events, error=error)
        container.chat_service = double
        return double

    try:
        yield install, container
    finally:
        container.chat_service = original


def _stream(client, headers, **payload):
    return client.post(
        "/api/v1/chat/stream",
        headers=headers,
        json={"message": "Hello", **payload},
    )


def test_stream_uses_the_sse_media_type(api_client, auth_headers, streamed):
    install, _ = streamed
    install()

    response = _stream(api_client, auth_headers())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


def test_stream_emits_thread_status_and_final_frames(api_client, auth_headers, streamed):
    install, _ = streamed
    install()

    events = parse(_stream(api_client, auth_headers()).text)
    names = [name for name, _ in events]

    assert names[0] == "thread"
    assert names[1] == "status"
    assert names[-1] == "final"
    assert events[0][1]["thread_id"]
    assert events[1][1]["status"] == "processing"
    assert events[-1][1]["title"] == "Greeting"


def test_tokens_stream_individually(api_client, auth_headers, streamed):
    install, _ = streamed
    install()

    events = parse(_stream(api_client, auth_headers()).text)
    tokens = [data["content"] for name, data in events if name == "token"]

    # Not one joined string: the provider chunks arrive as they did.
    assert tokens == ["Hel", "lo"]


def test_tool_events_are_mapped(api_client, auth_headers, streamed):
    install, _ = streamed
    install(
        events=[
            TurnEvent(
                type="tool_call",
                name="search_documents",
                content='{"query": "handbook"}',
            ),
            TurnEvent(
                type="tool_result", name="search_documents", content='{"count": 2}'
            ),
            TurnEvent(type="done", title=None),
        ]
    )

    events = parse(_stream(api_client, auth_headers()).text)
    by_name = dict(events)

    assert by_name["tool_start"]["tool"] == "search_documents"
    assert by_name["tool_start"]["arguments"] == {"query": "handbook"}
    assert by_name["tool_end"]["result"] == '{"count": 2}'


def test_an_interrupt_streams_an_approval_requirement(
    api_client, auth_headers, streamed
):
    install, container = streamed
    install(
        events=[
            TurnEvent(
                type="interrupt",
                name="approval",
                payload={
                    "tool": "update_product",
                    "title": "Update Product",
                    "interrupt_id": "int-1",
                    "approval_token": "graph-secret-token",
                    "arguments": {"product_id": "PRD-1001"},
                    "details": [["Price", "BDT 95,000"]],
                    "warnings": [],
                },
            )
        ]
    )
    thread = container.thread_service.create_thread("Mine", owner_id="alice")

    response = _stream(
        api_client, auth_headers(), thread_id=thread.thread_id
    )
    events = parse(response.text)
    approvals = [data for name, data in events if name == "approval_required"]

    assert approvals
    payload = approvals[0]
    assert payload["action"] == "update_product"
    assert payload["thread_id"] == thread.thread_id
    assert payload["approval_id"]
    assert payload["allowed_decisions"] == ["approve", "edit", "reject"]
    assert "graph-secret-token" not in response.text
    assert "approval_token" not in response.text


def test_a_service_error_becomes_an_error_frame(api_settings, auth_headers):
    from fastapi.testclient import TestClient

    from agentic_chatbot.api.main import create_app

    app = create_app(settings=api_settings)

    with TestClient(app, raise_server_exceptions=False) as client:
        container = app.state.container
        container.chat_service = ScriptedChatService(
            error=RuntimeError("secret provider detail sk-live-9")
        )
        token = client.post(
            "/api/v1/auth/token", json={"api_key": "alice-secret"}
        ).json()["access_token"]

        response = client.post(
            "/api/v1/chat/stream",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "Hello"},
        )

    events = parse(response.text)
    errors = [data for name, data in events if name == "error"]

    assert errors
    assert errors[0]["code"] == "STREAM_ERROR"
    assert "sk-live-9" not in response.text


def test_stream_requires_auth(api_client):
    assert (
        api_client.post(
            "/api/v1/chat/stream", json={"message": "Hello"}
        ).status_code
        == 401
    )


def test_stream_rejects_another_users_thread(api_client, auth_headers, streamed):
    install, container = streamed
    install()
    bobs = container.thread_service.create_thread("Bob", owner_id="bob")

    response = _stream(
        api_client, auth_headers(), thread_id=bobs.thread_id
    )

    assert response.status_code == 404
    assert bobs.thread_id not in response.text


def test_the_same_thread_id_is_used_throughout(api_client, auth_headers, streamed):
    install, container = streamed
    install()
    thread = container.thread_service.create_thread("Mine", owner_id="alice")

    events = parse(
        _stream(api_client, auth_headers(), thread_id=thread.thread_id).text
    )

    assert events[0][1]["thread_id"] == thread.thread_id
    assert all(
        name != "thread" or data["thread_id"] == thread.thread_id
        for name, data in events
    )


def test_the_lock_is_released_when_the_client_disconnects(
    api_client, auth_headers, streamed
):
    """Closing the generator must release the per-thread lock."""
    install, container = streamed
    install()
    thread = container.thread_service.create_thread("Mine", owner_id="alice")
    lock = container.thread_lock(thread.thread_id)

    response = _stream(
        api_client, auth_headers(), thread_id=thread.thread_id
    )
    assert parse(response.text)

    # TestClient consumed the whole stream, so the lock must be free again.
    assert lock.acquire(blocking=False) is True
    lock.release()


def test_a_busy_thread_reports_thread_busy(api_client, auth_headers, streamed):
    install, container = streamed
    install()
    thread = container.thread_service.create_thread("Mine", owner_id="alice")
    lock = container.thread_lock(thread.thread_id)
    lock.acquire()

    try:
        response = _stream(
            api_client, auth_headers(), thread_id=thread.thread_id
        )
        events = parse(response.text)
    finally:
        lock.release()

    assert [data["code"] for name, data in events if name == "error"] == [
        "THREAD_BUSY"
    ]


def test_frames_never_carry_internal_payloads():
    event = TurnEvent(
        type="interrupt",
        name="approval",
        payload={
            "tool": "update_product",
            "title": "Update Product",
            "approval_token": "must-not-leak",
            "operation_id": "thread:call",
        },
    )

    rendered = to_frame(event, "thread-1", "approval-id")

    assert "must-not-leak" not in rendered
    assert "approval_token" not in rendered
    assert sanitise(None) == {}
    assert sanitise({"a": 1, "approval_token": "x"}) == {"a": 1}


def test_frame_serialises_exotic_values():
    rendered = frame("x", {"value": object()})

    assert rendered.startswith("event: x\ndata: ")
    assert "object at" in rendered
