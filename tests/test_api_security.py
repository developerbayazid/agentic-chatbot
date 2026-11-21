"""Cross-cutting security assertions across every resource family.

Each resource has its own focused tests; this file states the invariants once,
in the places where a regression would be a security bug rather than a bug.
"""

from __future__ import annotations

from tests.test_api_approvals import PendingChatService


def test_no_response_ever_contains_an_approval_token(api_client, auth_headers):
    container = api_client.app.state.container
    original = container.chat_service
    container.chat_service = PendingChatService(token="the-graph-token")

    try:
        headers = auth_headers()
        stream = api_client.post(
            "/api/v1/chat/stream",
            headers=headers,
            json={"message": "Increase the price"},
        )
        listed = api_client.get("/api/v1/approvals", headers=headers)
        detail = api_client.get(
            f"/api/v1/approvals/{listed.json()[0]['approval_id']}",
            headers=headers,
        )
    finally:
        container.chat_service = original

    for response in (stream, listed, detail):
        assert "the-graph-token" not in response.text
        assert "approval_token" not in response.text


def test_ownership_cannot_be_supplied_by_a_client(api_client, auth_headers):
    """Every request schema forbids unknown fields, so identity is unreachable."""
    headers = auth_headers()

    chat = api_client.post(
        "/api/v1/chat",
        headers=headers,
        json={"message": "hi", "owner_id": "bob"},
    )
    thread = api_client.patch(
        "/api/v1/threads/whatever",
        headers=headers,
        json={"title": "x", "owner_id": "bob"},
    )
    decision = api_client.post(
        "/api/v1/approvals/whatever/decision",
        headers=headers,
        json={"decision": "approve", "owner_id": "bob"},
    )

    for response in (chat, thread, decision):
        assert response.status_code == 422
        assert "owner_id" in response.json()["error"]["message"]


def test_a_users_thread_list_never_includes_anothers(api_client, auth_headers):
    container = api_client.app.state.container
    container.thread_service.create_thread("Alice", owner_id="alice")
    container.thread_service.create_thread("Bob", owner_id="bob")

    alice = api_client.get("/api/v1/threads", headers=auth_headers()).json()
    bob = api_client.get(
        "/api/v1/threads", headers=auth_headers("bob-secret")
    ).json()

    assert [thread["title"] for thread in alice["threads"]] == ["Alice"]
    assert [thread["title"] for thread in bob["threads"]] == ["Bob"]


def test_retrieval_isolation_backs_the_document_endpoints(
    api_client, auth_headers
):
    """The REST list is not the only boundary: retrieval is scoped too."""
    alice = auth_headers()
    bob = auth_headers("bob-secret")
    api_client.post(
        "/api/v1/documents",
        headers=alice,
        files={"file": ("a.md", b"alpha onboarding handbook", "text/markdown")},
    )
    api_client.post(
        "/api/v1/documents",
        headers=bob,
        files={"file": ("b.md", b"beta onboarding handbook", "text/markdown")},
    )

    container = api_client.app.state.container
    alice_hits = container.document_service.search("onboarding", owner_id="alice")
    everything = container.document_service.search("onboarding")

    assert all("beta" not in hit.content for hit in alice_hits)
    assert any("beta" in hit.content for hit in everything)


def test_health_is_the_only_unauthenticated_surface(api_client):
    assert api_client.get("/health").status_code == 200
    assert api_client.get("/health/ready").status_code == 200

    guarded = ["/api/v1/threads", "/api/v1/approvals", "/api/v1/documents"]

    for path in guarded:
        assert api_client.get(path).status_code == 401

    assert api_client.post("/api/v1/chat", json={}).status_code == 401
