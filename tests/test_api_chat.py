"""Chat endpoint: thread creation/reuse, ownership, and event collection.

The chat service is replaced with a scripted double, so these tests make no
model call while still exercising the real event contract.
"""

from __future__ import annotations

import pytest

from agentic_chatbot.models import TurnEvent


class ScriptedChatService:
    """Emits a scripted event stream per turn, like ``ChatService``."""

    def __init__(self, events=None, error=None):
        self.events = events if events is not None else [
            TurnEvent(type="token", content="Hel"),
            TurnEvent(type="token", content="lo"),
            TurnEvent(type="done", title="Greeting"),
        ]
        self.error = error
        self.calls = []
        self.pending = {}

    def stream_turn(self, thread_id, user_message, owner_id=None):
        self.calls.append((thread_id, user_message, owner_id))

        if self.error is not None:
            raise self.error

        yield from self.events

    def resume_turn(self, thread_id, decision, owner_id=None):
        self.calls.append((thread_id, decision, owner_id))
        yield from self.events

    def get_pending_interrupt(self, thread_id, owner_id=None):
        return self.pending.get(thread_id)


@pytest.fixture
def scripted(api_client):
    """Swap the container's chat service for a scripted double."""
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


def test_a_message_creates_a_thread(api_client, auth_headers, scripted):
    install, container = scripted
    double = install()

    response = api_client.post(
        "/api/v1/chat", headers=auth_headers(), json={"message": "Hello"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Hello"
    assert body["status"] == "completed"
    assert body["title"] == "Greeting"
    assert body["approval_id"] is None

    created = container.thread_service.get_thread(body["thread_id"])
    assert created is not None
    assert created.owner_id == "alice"
    assert double.calls[0][2] == "alice"


def test_an_existing_thread_is_reused(api_client, auth_headers, scripted):
    install, container = scripted
    install()
    thread = container.thread_service.create_thread("Mine", owner_id="alice")

    response = api_client.post(
        "/api/v1/chat",
        headers=auth_headers(),
        json={"message": "Again", "thread_id": thread.thread_id},
    )

    assert response.status_code == 200
    assert response.json()["thread_id"] == thread.thread_id
    assert len(container.thread_service.list_threads(owner_id="alice")) == 1


def test_an_unknown_thread_is_404(api_client, auth_headers, scripted):
    install, _ = scripted
    install()

    response = api_client.post(
        "/api/v1/chat",
        headers=auth_headers(),
        json={"message": "Hello", "thread_id": "missing"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "THREAD_NOT_FOUND"


def test_another_users_thread_cannot_be_continued(api_client, auth_headers, scripted):
    install, container = scripted
    double = install()
    bobs = container.thread_service.create_thread("Bob", owner_id="bob")

    response = api_client.post(
        "/api/v1/chat",
        headers=auth_headers(),
        json={"message": "Continue", "thread_id": bobs.thread_id},
    )

    assert response.status_code == 404
    assert bobs.thread_id not in response.text
    assert double.calls == []


def test_a_pending_approval_blocks_a_new_message(api_client, auth_headers, scripted):
    install, container = scripted
    double = install()
    thread = container.thread_service.create_thread("Mine", owner_id="alice")
    double.pending[thread.thread_id] = {"interrupt_id": "i-1", "value": {}}

    response = api_client.post(
        "/api/v1/chat",
        headers=auth_headers(),
        json={"message": "Another", "thread_id": thread.thread_id},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPROVAL_PENDING"
    assert double.calls == []


def test_an_interrupt_is_reported_not_serialised(api_client, auth_headers, scripted):
    install, container = scripted
    payload = {
        "kind": "approval_request",
        "tool": "update_product",
        "title": "Update Product",
        "interrupt_id": "int-1",
        "approval_token": "graph-internal-token",
        "arguments": {"product_id": "PRD-1001"},
    }
    install(
        events=[
            TurnEvent(type="token", content="Checking."),
            TurnEvent(type="interrupt", name="approval", payload=payload),
        ]
    )

    response = api_client.post(
        "/api/v1/chat", headers=auth_headers(), json={"message": "Update it"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_approval"
    assert body["approval_id"]
    assert "approval_token" not in response.text
    assert "graph-internal-token" not in response.text


def test_an_llm_failure_is_a_500_without_internals(
    api_settings, auth_headers
):
    from fastapi.testclient import TestClient

    from agentic_chatbot.api.main import create_app

    app = create_app(settings=api_settings)

    with TestClient(app, raise_server_exceptions=False) as client:
        container = app.state.container
        container.chat_service = ScriptedChatService(
            error=RuntimeError("provider said: invalid api key sk-live-123")
        )

        token = client.post(
            "/api/v1/auth/token", json={"api_key": "alice-secret"}
        ).json()["access_token"]
        response = client.post(
            "/api/v1/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "Hello"},
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "sk-live-123" not in response.text


@pytest.mark.parametrize("message", ["", "   "])
def test_an_empty_message_is_rejected(api_client, auth_headers, scripted, message):
    install, _ = scripted
    install()

    response = api_client.post(
        "/api/v1/chat", headers=auth_headers(), json={"message": message}
    )

    assert response.status_code in (422,)


def test_a_client_cannot_supply_an_owner(api_client, auth_headers, scripted):
    install, _ = scripted
    install()

    response = api_client.post(
        "/api/v1/chat",
        headers=auth_headers(),
        json={"message": "Hello", "owner_id": "bob"},
    )

    assert response.status_code == 422
    assert "owner_id" in response.json()["error"]["message"]


def test_chat_requires_auth(api_client):
    assert (
        api_client.post("/api/v1/chat", json={"message": "Hello"}).status_code
        == 401
    )


def test_concurrent_messages_on_different_threads_both_complete(
    api_client, auth_headers, scripted
):
    """Different conversations must not serialize behind each other."""
    import threading

    install, container = scripted
    install()
    headers = auth_headers()
    first = container.thread_service.create_thread("One", owner_id="alice")
    second = container.thread_service.create_thread("Two", owner_id="alice")
    results = {}

    def send(thread_id):
        results[thread_id] = api_client.post(
            "/api/v1/chat",
            headers=headers,
            json={"message": "Hello", "thread_id": thread_id},
        ).status_code

    threads = [
        threading.Thread(target=send, args=(thread.thread_id,))
        for thread in (first, second)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(timeout=20)

    assert results == {first.thread_id: 200, second.thread_id: 200}
