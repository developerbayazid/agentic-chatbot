"""CLI approval panel and approve/edit/reject interaction."""

from rich.console import Console

from agentic_chatbot.cli import console as ui
from agentic_chatbot.cli.approval import prompt_decision
from agentic_chatbot.cli.chat import process_message, resume_pending
from agentic_chatbot.models import TurnEvent

PAYLOAD = {
    "kind": "approval_request",
    "tool": "update_product",
    "title": "Update Product",
    "arguments": {"product_id": "PRD-1001", "selling_price": 95000},
    "details": [
        ["Product", "Latitude Business Laptop 14"],
        ["SKU", "LAP-BIZ-14-001"],
        ["Current Selling Price", "BDT 89,500"],
        ["Proposed Selling Price", "BDT 95,000"],
    ],
    "warnings": [],
    "approval_token": "token-1",
    "requested_by": "AI Agent",
    "reason": "The agent requested a sensitive inventory operation.",
}


class FakeChatService:
    def __init__(self, first_events=(), resumed_events=(), pending=None):
        self.first_events = list(first_events)
        self.resumed_events = list(resumed_events)
        self.pending = pending
        self.resume_calls = []
        self.stream_calls = []

    def stream_turn(self, thread_id, user_message):
        self.stream_calls.append((thread_id, user_message))
        yield from self.first_events

    def resume_turn(self, thread_id, decision):
        self.resume_calls.append((thread_id, decision))
        yield from self.resumed_events

    def get_pending_interrupt(self, thread_id):
        return self.pending


class PendingFakeChatService(FakeChatService):
    """Clears the pending interrupt when a resume actually happens."""

    def resume_turn(self, thread_id, decision):
        self.resume_calls.append((thread_id, decision))
        self.pending = None
        yield from self.resumed_events


def answers(*values):
    iterator = iter(values)
    return lambda question: next(iterator)


def test_panel_clearly_shows_the_action_and_decisions():
    console = Console(width=100, record=True)

    ui.approval_panel(console, PAYLOAD)
    text = console.export_text()

    assert "HUMAN APPROVAL REQUIRED" in text
    assert "Action: Update Product" in text
    assert "Latitude Business Laptop 14" in text
    assert "Current Selling Price" in text
    assert "Proposed Selling Price" in text
    assert "[A] Approve" in text
    assert "[E] Edit Arguments" in text
    assert "[R] Reject" in text


def test_approve_returns_the_approval_token():
    console = Console(width=100)

    decision = prompt_decision(
        console, answers("a", "looks good"), PAYLOAD
    )

    assert decision == {
        "action": "approve",
        "approval_token": "token-1",
        "comment": "looks good",
    }


def test_slash_decision_words_are_accepted():
    console = Console(width=100)

    decision = prompt_decision(console, answers("/approve", ""), PAYLOAD)

    assert decision["action"] == "approve"


def test_reject_collects_a_reason():
    console = Console(width=100)

    decision = prompt_decision(console, answers("r", "too expensive"), PAYLOAD)

    assert decision["action"] == "reject"
    assert decision["comment"] == "too expensive"
    assert decision["approval_token"] == "token-1"


def test_edit_parses_arguments_and_confirms():
    console = Console(width=100)

    decision = prompt_decision(
        console, answers("e", "2", "97000", "", "y"), PAYLOAD
    )

    assert decision["action"] == "edit"
    assert decision["arguments"]["product_id"] == "PRD-1001"
    assert decision["arguments"]["selling_price"] == 97000
    assert decision["approval_token"] == "token-1"


def test_edit_can_change_a_string_field():
    console = Console(width=100)
    payload = {
        **PAYLOAD,
        "arguments": {"product_id": "PRD-1001", "name": "Old Name"},
        "editable_fields": ["product_id", "name"],
        "field_types": {"product_id": "string", "name": "string"},
    }

    decision = prompt_decision(
        console,
        answers("e", "2", "Latitude Business Laptop 14 Pro", "", "y"),
        payload,
    )

    assert decision["action"] == "edit"
    assert decision["arguments"]["name"] == "Latitude Business Laptop 14 Pro"


def test_edit_can_be_cancelled_and_returns_to_the_decision_menu():
    console = Console(width=100)

    decision = prompt_decision(console, answers("e", "c", "a", ""), PAYLOAD)

    assert decision["action"] == "approve"


def test_invalid_field_value_is_reported_and_recovery_is_possible():
    console = Console(width=100, record=True)

    decision = prompt_decision(
        console, answers("e", "2", "not-a-number", "", "a", ""), PAYLOAD
    )

    text = console.export_text()
    assert "Invalid value" in text
    assert decision["action"] == "approve"


def test_blank_or_missing_input_leaves_the_action_pending():
    console = Console(width=100, record=True)

    assert prompt_decision(console, answers(""), PAYLOAD) is None
    assert "not executed" not in console.export_text().lower()

    console.clear()
    assert prompt_decision(console, None, PAYLOAD) is None
    assert "not executed" in console.export_text().lower()


def test_process_message_resumes_after_an_interrupt():
    console = Console(width=100, record=True)
    service = FakeChatService(
        first_events=[
            TurnEvent(type="token", content="I will update the price."),
            TurnEvent(type="interrupt", name="approval", payload=PAYLOAD),
            TurnEvent(type="done"),
        ],
        resumed_events=[
            TurnEvent(
                type="tool_result",
                name="update_product",
                content='{"product": {"selling_price": 95000}}',
            ),
            TurnEvent(type="token", content=" Price updated."),
            TurnEvent(type="done"),
        ],
    )

    process_message(console, service, "thread-1", "raise price", answers("a", ""))

    text = console.export_text()
    assert "HUMAN APPROVAL REQUIRED" in text
    assert len(service.resume_calls) == 1
    thread_id, decision = service.resume_calls[0]
    assert thread_id == "thread-1"
    assert decision["action"] == "approve"
    assert "Price updated." in text


def test_process_message_does_not_resume_when_the_human_cancels():
    console = Console(width=100, record=True)
    service = FakeChatService(
        first_events=[
            TurnEvent(type="interrupt", name="approval", payload=PAYLOAD),
            TurnEvent(type="done"),
        ]
    )

    process_message(console, service, "thread-1", "raise price", answers(""))

    text = console.export_text()
    assert service.resume_calls == []
    assert "not executed" in text.lower()


def test_rejection_resumes_the_graph_without_executing():
    console = Console(width=100)
    service = FakeChatService(
        first_events=[
            TurnEvent(type="interrupt", name="approval", payload=PAYLOAD),
            TurnEvent(type="done"),
        ],
        resumed_events=[
            TurnEvent(type="tool_result", name="update_product", content="Action rejected."),
            TurnEvent(type="token", content=" Nothing was changed."),
            TurnEvent(type="done"),
        ],
    )

    process_message(console, service, "thread-1", "raise price", answers("r", "no"))

    assert service.resume_calls[0][1]["action"] == "reject"


def test_resume_pending_handles_an_approval_left_by_a_previous_process():
    console = Console(width=100, record=True)
    service = FakeChatService(
        pending={"interrupt_id": "int-1", "value": PAYLOAD},
        resumed_events=[
            TurnEvent(type="token", content="Applied after restart."),
            TurnEvent(type="done"),
        ],
    )

    handled = resume_pending(console, service, "thread-9", answers("a", ""))

    text = console.export_text()
    assert handled is True
    assert "still awaiting human approval" in text
    assert service.resume_calls[0][1]["action"] == "approve"
    assert "Applied after restart." in text


def test_resume_pending_without_an_interrupt_does_nothing():
    console = Console(width=100)
    service = FakeChatService()

    assert resume_pending(console, service, "thread-1", answers()) is False
    assert service.resume_calls == []


def test_new_message_resolves_a_pending_approval_first():
    console = Console(width=100, record=True)
    service = PendingFakeChatService(
        pending={"interrupt_id": "int-1", "value": PAYLOAD},
        first_events=[
            TurnEvent(type="token", content="New answer."),
            TurnEvent(type="done"),
        ],
        resumed_events=[
            TurnEvent(type="token", content="Applied first."),
            TurnEvent(type="done"),
        ],
    )

    process_message(
        console, service, "thread-1", "new question", answers("a", "")
    )

    assert service.resume_calls[0][1]["action"] == "approve"
    assert service.stream_calls == [("thread-1", "new question")]
    text = console.export_text()
    assert "Applied first." in text
    assert "New answer." in text


def test_new_message_is_not_sent_while_an_approval_stays_pending():
    console = Console(width=100, record=True)
    service = PendingFakeChatService(
        pending={"interrupt_id": "int-1", "value": PAYLOAD},
        first_events=[TurnEvent(type="done")],
    )

    process_message(console, service, "thread-1", "new question", answers(""))

    assert service.resume_calls == []
    assert service.stream_calls == []
    text = console.export_text()
    assert "not sent" in text.lower()
