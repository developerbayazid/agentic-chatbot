"""HITL approvals over HTTP.

These tests drive real pending interrupts: the chat double reports a pending
interrupt, and the router must bind a decision to it before resuming.
"""

from __future__ import annotations

import threading

import pytest

from agentic_chatbot.models import TurnEvent


class PendingChatService:
    """A chat double whose thread is waiting on one approval interrupt."""

    def __init__(self, tool="update_product", arguments=None, token="graph-token"):
        self.payload = {
            "kind": "approval_request",
            "tool": tool,
            "title": tool.replace("_", " ").title(),
            "tool_call_id": "call-1",
            "interrupt_id": "interrupt-1",
            "approval_token": token,
            "arguments": arguments or {"product_id": "PRD-1001"},
            "editable_fields": ["product_id", "selling_price"],
            "field_types": {"product_id": "string", "selling_price": "integer"},
            "details": [["Current Selling Price", "BDT 89,500"]],
            "warnings": [],
            "requested_by": "AI Agent",
            "reason": "The agent requested a sensitive inventory operation.",
        }
        self.pending = False
        self.resumes = []

    def get_pending_interrupt(self, thread_id, owner_id=None):
        if not self.pending:
            return None

        return {"interrupt_id": "interrupt-1", "value": self.payload}

    def stream_turn(self, thread_id, message, owner_id=None):
        self.pending = True
        yield TurnEvent(type="token", content="Proposed.")
        yield TurnEvent(type="interrupt", name="approval", payload=self.payload)

    def resume_turn(self, thread_id, decision, owner_id=None):
        self.resumes.append(decision)
        self.pending = False
        yield TurnEvent(type="token", content="Executed.")
        yield TurnEvent(type="done")


@pytest.fixture
def approval(api_client):
    container = api_client.app.state.container
    original = container.chat_service

    def install(**kwargs):
        double = PendingChatService(**kwargs)
        container.chat_service = double
        return double

    try:
        yield install, container
    finally:
        container.chat_service = original


def _start_approval(client, headers, double, container, subject="alice"):
    """Create a thread and put it into the pending state."""
    thread = container.thread_service.create_thread("Mine", owner_id=subject)
    stream = client.post(
        "/api/v1/chat/stream",
        headers=headers,
        json={"thread_id": thread.thread_id, "message": "Increase the price"},
    )
    assert stream.status_code == 200
    assert double.pending
    return thread


def _approval_id(client, headers):
    listed = client.get("/api/v1/approvals", headers=headers)
    assert listed.status_code == 200
    return listed.json()[0]["approval_id"]


def test_pending_approvals_are_listed(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    headers = auth_headers()
    _start_approval(api_client, headers, double, container)

    listed = api_client.get("/api/v1/approvals", headers=headers).json()

    assert len(listed) == 1
    assert listed[0]["action"] == "update_product"
    assert listed[0]["title"] == "Update Product"
    assert listed[0]["approval_id"]
    assert listed[0]["allowed_decisions"] == ["approve", "edit", "reject"]


def test_approval_detail_includes_edit_metadata(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    headers = auth_headers()
    _start_approval(api_client, headers, double, container)
    approval_id = _approval_id(api_client, headers)

    detail = api_client.get(
        f"/api/v1/approvals/{approval_id}", headers=headers
    ).json()

    assert detail["editable_fields"] == ["product_id", "selling_price"]
    assert detail["field_types"]["selling_price"] == "integer"
    assert detail["details"] == [["Current Selling Price", "BDT 89,500"]]
    assert "approval_token" not in str(detail)


def test_listing_is_empty_without_a_pending_interrupt(api_client, auth_headers, approval):
    install, container = approval
    install()
    headers = auth_headers()
    container.thread_service.create_thread("Mine", owner_id="alice")

    assert api_client.get("/api/v1/approvals", headers=headers).json() == []


def test_name_another_users_approval_is_not_found(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    bob = container.thread_service.create_thread("Bob", owner_id="bob")

    # Bob's interrupt, signed for Bob, using the same double.
    double.payload["approval_token"] = "bob-graph-token"
    double.pending = True

    from agentic_chatbot.api.security import handle_for

    settings = api_client.app.state.settings
    bobs_handle = handle_for(
        settings,
        "bob",
        bob.thread_id,
        double.get_pending_interrupt(bob.thread_id, owner_id="bob"),
    )

    alice = auth_headers()
    response = api_client.get(f"/api/v1/approvals/{bobs_handle}", headers=alice)

    assert response.status_code == 404
    assert bob.thread_id not in response.text


def test_approve_resumes_the_original_thread(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    headers = auth_headers()
    thread = _start_approval(api_client, headers, double, container)
    approval_id = _approval_id(api_client, headers)

    response = api_client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=headers,
        json={"decision": "approve", "comment": "Looks right."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["thread_id"] == thread.thread_id
    assert body["response"] == "Executed."
    assert double.resumes[0]["action"] == "approve"
    assert double.resumes[0]["comment"] == "Looks right."
    # The token is copied from the live interrupt, never from the request.
    assert double.resumes[0]["approval_token"] == "graph-token"


def test_edit_sends_the_reviewed_arguments(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    headers = auth_headers()
    _start_approval(api_client, headers, double, container)
    approval_id = _approval_id(api_client, headers)

    response = api_client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=headers,
        json={
            "decision": "edit",
            "edited_arguments": {"selling_price": 95000},
        },
    )

    assert response.status_code == 200
    assert double.resumes[0]["action"] == "edit"
    assert double.resumes[0]["arguments"] == {"selling_price": 95000}


def test_reject_executes_nothing(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    headers = auth_headers()
    _start_approval(api_client, headers, double, container)
    approval_id = _approval_id(api_client, headers)

    response = api_client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=headers,
        json={"decision": "reject", "comment": "Price is wrong."},
    )

    assert response.status_code == 200
    assert double.resumes[0]["action"] == "reject"
    assert double.resumes[0]["comment"] == "Price is wrong."


def test_respond_is_refused_rather_than_mapped(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    headers = auth_headers()
    _start_approval(api_client, headers, double, container)
    approval_id = _approval_id(api_client, headers)

    response = api_client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=headers,
        json={"decision": "respond", "response": "Use Dhaka."},
    )

    assert response.status_code == 422
    assert double.resumes == []
    assert double.pending is True


def test_an_edit_without_arguments_is_invalid(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    headers = auth_headers()
    _start_approval(api_client, headers, double, container)
    approval_id = _approval_id(api_client, headers)

    response = api_client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=headers,
        json={"decision": "edit"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_DECISION"
    assert double.resumes == []


def test_edited_arguments_are_refused_for_approve(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    headers = auth_headers()
    _start_approval(api_client, headers, double, container)
    approval_id = _approval_id(api_client, headers)

    response = api_client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=headers,
        json={"decision": "approve", "edited_arguments": {"x": 1}},
    )

    assert response.status_code == 422
    assert double.resumes == []


def test_a_duplicate_decision_executes_once(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    headers = auth_headers()
    _start_approval(api_client, headers, double, container)
    approval_id = _approval_id(api_client, headers)

    first = api_client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=headers,
        json={"decision": "approve"},
    )
    second = api_client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=headers,
        json={"decision": "approve"},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "APPROVAL_NOT_PENDING"
    assert len(double.resumes) == 1


def test_concurrent_decisions_execute_once(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    headers = auth_headers()
    _start_approval(api_client, headers, double, container)
    approval_id = _approval_id(api_client, headers)
    statuses = []

    def decide():
        statuses.append(
            api_client.post(
                f"/api/v1/approvals/{approval_id}/decision",
                headers=headers,
                json={"decision": "approve"},
            ).status_code
        )

    threads = [threading.Thread(target=decide) for _ in range(4)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(timeout=20)

    assert len(double.resumes) == 1
    assert statuses.count(200) == 1
    assert all(status in (200, 409) for status in statuses)


def test_a_stale_handle_cannot_execute(api_client, auth_headers, approval):
    """If the proposal changes, the old handle stops matching it."""
    install, container = approval
    double = install()
    headers = auth_headers()
    _start_approval(api_client, headers, double, container)
    stale = _approval_id(api_client, headers)

    # The agent revises what it is asking for; the graph token changes with it.
    double.payload["approval_token"] = "a-different-graph-token"
    double.payload["arguments"] = {"product_id": "PRD-1001", "selling_price": 1}

    response = api_client.post(
        f"/api/v1/approvals/{stale}/decision",
        headers=headers,
        json={"decision": "approve"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPROVAL_NOT_PENDING"
    assert double.resumes == []


def test_a_tampered_handle_is_rejected(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    headers = auth_headers()
    _start_approval(api_client, headers, double, container)
    approval_id = _approval_id(api_client, headers)
    tampered = ("A" if approval_id[0] != "A" else "B") + approval_id[1:]

    response = api_client.post(
        f"/api/v1/approvals/{tampered}/decision",
        headers=headers,
        json={"decision": "approve"},
    )

    assert response.status_code == 409
    assert double.resumes == []


def test_a_malformed_handle_is_rejected(api_client, auth_headers, approval):
    install, _ = approval
    install()

    response = api_client.post(
        "/api/v1/approvals/not a handle!!/decision",
        headers=auth_headers(),
        json={"decision": "approve"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "APPROVAL_INVALID"


def test_another_users_handle_cannot_be_used(api_client, auth_headers, approval):
    install, container = approval
    double = install()
    bob_headers = auth_headers("bob-secret")
    bobs_thread = _start_approval(
        api_client, bob_headers, double, container, subject="bob"
    )
    bobs_handle = _approval_id(api_client, bob_headers)

    response = api_client.post(
        f"/api/v1/approvals/{bobs_handle}/decision",
        headers=auth_headers(),
        json={"decision": "approve"},
    )

    assert response.status_code == 409
    assert double.resumes == []
    assert bobs_thread.thread_id not in response.text


def test_approvals_require_auth(api_client):
    assert api_client.get("/api/v1/approvals").status_code == 401
    assert (
        api_client.post(
            "/api/v1/approvals/x/decision", json={"decision": "approve"}
        ).status_code
        == 401
    )
