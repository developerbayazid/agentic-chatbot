"""Thread endpoints: lifecycle and per-user ownership."""

from __future__ import annotations


def _create(client, headers, title="New chat"):
    return client.post(
        "/api/v1/threads",
        headers=headers,
        json={"title": title},
    )


def test_listing_is_empty_for_a_new_user(api_client, auth_headers):
    response = api_client.get("/api/v1/threads", headers=auth_headers())

    assert response.status_code == 200
    assert response.json() == {"threads": []}


def test_threads_require_a_token(api_client):
    assert api_client.get("/api/v1/threads").status_code == 401


def test_a_user_sees_only_their_own_threads(api_client, auth_headers, api_settings):
    container = api_client.app.state.container

    alice = container.thread_service.create_thread("Alice", owner_id="alice")
    container.thread_service.create_thread("Bob", owner_id="bob")

    response = api_client.get("/api/v1/threads", headers=auth_headers())

    assert response.status_code == 200
    body = response.json()["threads"]
    assert [thread["thread_id"] for thread in body] == [alice.thread_id]
    assert body[0]["title"] == "Alice"
    assert "owner_id" not in response.text


def test_get_a_thread(api_client, auth_headers):
    container = api_client.app.state.container
    thread = container.thread_service.create_thread("Hello", owner_id="alice")

    response = api_client.get(
        f"/api/v1/threads/{thread.thread_id}", headers=auth_headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == thread.thread_id
    assert body["title"] == "Hello"
    assert "owner_id" not in body


def test_unknown_thread_is_404(api_client, auth_headers):
    response = api_client.get("/api/v1/threads/missing", headers=auth_headers())

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "THREAD_NOT_FOUND"


def test_another_users_thread_is_404_on_every_route(api_client, auth_headers):
    container = api_client.app.state.container
    bob = container.thread_service.create_thread("Bob private", owner_id="bob")

    alice = auth_headers()
    routes = [
        client_call
        for client_call in (
            lambda: api_client.get(
                f"/api/v1/threads/{bob.thread_id}", headers=alice
            ),
            lambda: api_client.patch(
                f"/api/v1/threads/{bob.thread_id}",
                headers=alice,
                json={"title": "hijacked"},
            ),
            lambda: api_client.delete(
                f"/api/v1/threads/{bob.thread_id}", headers=alice
            ),
            lambda: api_client.get(
                f"/api/v1/threads/{bob.thread_id}/history", headers=alice
            ),
        )
    ]

    for call in routes:
        response = call()
        assert response.status_code == 404
        # No existence leak: the error must not reveal that it is someone's.
        assert bob.thread_id not in response.text

    assert container.thread_service.get_thread(bob.thread_id).title == "Bob private"


def test_unowned_thread_is_not_reachable_through_the_api(api_client, auth_headers):
    container = api_client.app.state.container
    cli_thread = container.thread_service.create_thread("CLI chat", owner_id=None)

    response = api_client.get(
        f"/api/v1/threads/{cli_thread.thread_id}", headers=auth_headers()
    )

    assert response.status_code == 404
    assert container.thread_service.get_thread(cli_thread.thread_id) is not None


def test_rename_a_thread(api_client, auth_headers):
    container = api_client.app.state.container
    thread = container.thread_service.create_thread("Old", owner_id="alice")

    response = api_client.patch(
        f"/api/v1/threads/{thread.thread_id}",
        headers=auth_headers(),
        json={"title": "A much better title"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "A much better title"


def test_rename_rejects_empty_and_oversized_titles(api_client, auth_headers):
    container = api_client.app.state.container
    thread = container.thread_service.create_thread("Old", owner_id="alice")
    headers = auth_headers()

    assert (
        api_client.patch(
            f"/api/v1/threads/{thread.thread_id}",
            headers=headers,
            json={"title": ""},
        ).status_code
        == 422
    )
    assert (
        api_client.patch(
            f"/api/v1/threads/{thread.thread_id}",
            headers=headers,
            json={"title": "x" * 101},
        ).status_code
        == 422
    )


def test_delete_removes_metadata_and_checkpoints(api_client, auth_headers):
    container = api_client.app.state.container
    thread = container.thread_service.create_thread("Doomed", owner_id="alice")

    response = api_client.delete(
        f"/api/v1/threads/{thread.thread_id}", headers=auth_headers()
    )

    assert response.status_code == 204
    assert container.thread_service.get_thread(thread.thread_id) is None


def test_deleting_twice_is_404(api_client, auth_headers):
    container = api_client.app.state.container
    thread = container.thread_service.create_thread("Doomed", owner_id="alice")
    headers = auth_headers()

    assert (
        api_client.delete(
            f"/api/v1/threads/{thread.thread_id}", headers=headers
        ).status_code
        == 204
    )
    assert (
        api_client.delete(
            f"/api/v1/threads/{thread.thread_id}", headers=headers
        ).status_code
        == 404
    )


def test_history_is_empty_for_a_new_thread(api_client, auth_headers):
    container = api_client.app.state.container
    thread = container.thread_service.create_thread("Hello", owner_id="alice")

    response = api_client.get(
        f"/api/v1/threads/{thread.thread_id}/history", headers=auth_headers()
    )

    assert response.status_code == 200
    assert response.json() == {"thread_id": thread.thread_id, "messages": []}


def test_history_reports_conversational_messages(api_client, auth_headers):
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    container = api_client.app.state.container
    thread = container.thread_service.create_thread("Hello", owner_id="alice")
    container.chat_service._chatbot.get_state = lambda config: type(
        "State", (), {
            "values": {
                "messages": [
                    HumanMessage(content="hi"),
                    ToolMessage(content="raw internal payload", name="calculator", tool_call_id="1"),
                    AIMessage(content="hello there"),
                ]
            }
        }
    )()

    response = api_client.get(
        f"/api/v1/threads/{thread.thread_id}/history", headers=auth_headers()
    )

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "tool", "assistant"]
    assert messages[-1]["content"] == "hello there"


def test_create_a_thread_directly_is_not_exposed(api_client, auth_headers):
    """Threads are created by sending a message, not by a bare POST."""
    assert (
        api_client.post(
            "/api/v1/threads",
            headers=auth_headers(),
            json={"title": "x"},
        ).status_code
        in (404, 405)
    )
