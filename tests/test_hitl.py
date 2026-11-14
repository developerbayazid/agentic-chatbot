"""HITL: interrupts, decisions, resume, persistence, and idempotency."""

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from agentic_chatbot.database import create_connection
from agentic_chatbot.graph.workflow import build_chatbot
from agentic_chatbot.inventory.approvals import SENSITIVE_TOOLS
from agentic_chatbot.inventory.tools import create_inventory_tools
from agentic_chatbot.models import TurnEvent
from agentic_chatbot.services.chat_service import ChatService
from tests.fakes import FakeThreadService, FakeTitleService


class ScriptedLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(list(messages))
        if self.responses:
            return self.responses.pop(0)
        return AIMessage(content="Done.")


def tool_call(name, args, call_id):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id}],
    )


def build(service, responses, checkpointer=None):
    tools = create_inventory_tools(service)
    llm = ScriptedLLM(responses)
    graph = build_chatbot(
        llm,
        checkpointer or InMemorySaver(),
        tools,
        sensitive_tools=SENSITIVE_TOOLS,
        preview_operation=service.preview_operation,
        record_decision=service.record_hitl_decision,
    )
    return graph, llm


def payload_for(graph, thread_id):
    state = graph.get_state({"configurable": {"thread_id": thread_id}})
    for task in state.tasks:
        for item in task.interrupts:
            return item.value
    return None


def price_of(service, product_id="PRD-1001"):
    return service.get_product(product_id)["product"]["selling_price"]


def test_sensitive_call_interrupts_before_execution(inventory_service):
    graph, _ = build(
        inventory_service,
        [
            tool_call(
                "update_product",
                {"product_id": "PRD-1001", "selling_price": 95000},
                "call-price",
            ),
            AIMessage(content="Updated."),
        ],
    )
    thread = "thread-approve"
    config = {"configurable": {"thread_id": thread}}

    result = graph.invoke(
        {"messages": [HumanMessage(content="Increase the price to 95000")]},
        config=config,
    )

    assert "__interrupt__" in result
    payload = payload_for(graph, thread)
    assert payload["tool"] == "update_product"
    assert payload["arguments"]["selling_price"] == 95000
    assert "selling_price" in payload["editable_fields"]
    assert "selling_price" in payload["field_types"]
    assert payload["details"][-2] == ["Current Selling Price", "BDT 89,500"]
    assert payload["details"][-1] == ["Proposed Selling Price", "BDT 95,000"]
    assert price_of(inventory_service) == 89500

    graph.invoke(
        Command(
            resume={
                "action": "approve",
                "approval_token": payload["approval_token"],
                "comment": "Approved by test",
            }
        ),
        config=config,
    )

    assert price_of(inventory_service) == 95000
    messages = graph.get_state(config).values["messages"]
    assert messages[-1].content == "Updated."
    assert any(
        isinstance(message, ToolMessage) and message.name == "update_product"
        for message in messages
    )
    assert inventory_service.store.snapshot()["audit_log"][-1]["action"] == (
        "approval_granted"
    )


def test_rejection_does_not_execute_the_operation(inventory_service):
    graph, _ = build(
        inventory_service,
        [
            tool_call(
                "update_product",
                {"product_id": "PRD-1001", "selling_price": 95000},
                "call-reject",
            ),
            AIMessage(content="Nothing changed."),
        ],
    )
    thread = "thread-reject"
    config = {"configurable": {"thread_id": thread}}
    graph.invoke({"messages": [HumanMessage(content="raise price")]}, config=config)
    payload = payload_for(graph, thread)

    graph.invoke(
        Command(
            resume={
                "action": "reject",
                "approval_token": payload["approval_token"],
                "comment": "Too expensive",
            }
        ),
        config=config,
    )

    assert price_of(inventory_service) == 89500
    tool_messages = [
        message
        for message in graph.get_state(config).values["messages"]
        if isinstance(message, ToolMessage)
    ]
    assert "rejected" in tool_messages[-1].content.lower()
    assert "Too expensive" in tool_messages[-1].content
    assert inventory_service.store.snapshot()["audit_log"][-1]["action"] == (
        "approval_rejected"
    )


def test_edited_arguments_are_executed(inventory_service):
    graph, _ = build(
        inventory_service,
        [
            tool_call(
                "update_product",
                {"product_id": "PRD-1001", "selling_price": 95000},
                "call-edit",
            ),
            AIMessage(content="Updated with edited arguments."),
        ],
    )
    thread = "thread-edit"
    config = {"configurable": {"thread_id": thread}}
    graph.invoke({"messages": [HumanMessage(content="raise price")]}, config=config)
    payload = payload_for(graph, thread)

    graph.invoke(
        Command(
            resume={
                "action": "edit",
                "arguments": {"product_id": "PRD-1001", "selling_price": 97000},
                "approval_token": payload["approval_token"],
                "comment": "Use 97000 instead",
            }
        ),
        config=config,
    )

    assert price_of(inventory_service) == 97000
    assert inventory_service.store.snapshot()["audit_log"][-1]["action"] == (
        "approval_edited"
    )


def test_stale_approval_is_not_executed(inventory_service):
    graph, _ = build(
        inventory_service,
        [
            tool_call(
                "update_product",
                {"product_id": "PRD-1001", "selling_price": 95000},
                "call-stale",
            ),
            AIMessage(content="The approval was stale."),
        ],
    )
    thread = "thread-stale"
    config = {"configurable": {"thread_id": thread}}
    graph.invoke({"messages": [HumanMessage(content="raise price")]}, config=config)

    graph.invoke(
        Command(resume={"action": "approve", "approval_token": "not-the-token"}),
        config=config,
    )

    assert price_of(inventory_service) == 89500
    tool_messages = [
        message
        for message in graph.get_state(config).values["messages"]
        if isinstance(message, ToolMessage)
    ]
    assert "does not match the current proposal" in tool_messages[-1].content
    assert inventory_service.store.snapshot()["audit_log"][-1]["result"] == "failed"


def test_multiple_pending_approvals_are_resolved_one_at_a_time(inventory_service):
    graph, _ = build(
        inventory_service,
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "update_product",
                        "args": {"product_id": "PRD-1001", "selling_price": 95000},
                        "id": "call-a",
                    },
                    {
                        "name": "update_product",
                        "args": {"product_id": "PRD-1002", "selling_price": 115000},
                        "id": "call-b",
                    },
                ],
            ),
            AIMessage(content="Both updated."),
        ],
    )
    thread = "thread-multiple"
    config = {"configurable": {"thread_id": thread}}
    graph.invoke({"messages": [HumanMessage(content="raise two prices")]}, config=config)

    first = payload_for(graph, thread)
    assert first["tool_call_id"] == "call-a"
    graph.invoke(
        Command(
            resume={"action": "approve", "approval_token": first["approval_token"]}
        ),
        config=config,
    )

    second = payload_for(graph, thread)
    assert second is not None
    assert second["tool_call_id"] == "call-b"
    assert price_of(inventory_service, "PRD-1002") == 112000

    graph.invoke(
        Command(
            resume={"action": "approve", "approval_token": second["approval_token"]}
        ),
        config=config,
    )

    assert price_of(inventory_service, "PRD-1001") == 95000
    assert price_of(inventory_service, "PRD-1002") == 115000
    assert graph.get_state(config).values["messages"][-1].content == "Both updated."


def test_discount_approval_updates_sale_totals(inventory_service):
    graph, _ = build(
        inventory_service,
        [
            tool_call(
                "update_sale",
                {"sale_id": "SALE-2026-010", "discount": 5000},
                "call-discount",
            ),
            AIMessage(content="Discount approved."),
        ],
    )
    thread = "thread-discount"
    config = {"configurable": {"thread_id": thread}}
    graph.invoke(
        {"messages": [HumanMessage(content="Apply a 5000 discount")]},
        config=config,
    )

    payload = payload_for(graph, thread)
    details = dict(payload["details"])
    assert details["Current Discount"] == "BDT 3,000"
    assert details["Proposed Discount"] == "BDT 5,000"
    assert details["Projected Total"].startswith("BDT ")

    graph.invoke(
        Command(
            resume={
                "action": "approve",
                "approval_token": payload["approval_token"],
            }
        ),
        config=config,
    )

    sale = inventory_service.get_sale("SALE-2026-010")["sale"]
    assert sale["discount"] == 5000
    taxable = sale["subtotal"] - 5000
    assert sale["total"] == taxable + (taxable * 5 + 50) // 100
    assert graph.get_state(config).values["messages"][-1].content == (
        "Discount approved."
    )


def test_stock_adjustment_approval_updates_stock_and_movement(inventory_service):
    before = inventory_service.get_stock("PRD-1009", "WH-001")["stock"][0][
        "quantity_on_hand"
    ]
    graph, _ = build(
        inventory_service,
        [
            tool_call(
                "adjust_stock",
                {
                    "product_id": "PRD-1009",
                    "warehouse_id": "WH-001",
                    "quantity_change": -4,
                    "reason": "Damaged units",
                    "performed_by": "EMP-004",
                },
                "call-stock",
            ),
            AIMessage(content="Stock adjusted."),
        ],
    )
    thread = "thread-stock-approve"
    config = {"configurable": {"thread_id": thread}}
    graph.invoke(
        {"messages": [HumanMessage(content="Reduce stock by 4")]},
        config=config,
    )

    payload = payload_for(graph, thread)
    assert ["Warehouse", "WH-001"] in payload["details"]
    assert ["Quantity Change", -4] in payload["details"]
    assert payload["arguments"]["reason"] == "Damaged units"

    graph.invoke(
        Command(
            resume={
                "action": "approve",
                "approval_token": payload["approval_token"],
            }
        ),
        config=config,
    )

    after = inventory_service.get_stock("PRD-1009", "WH-001")["stock"][0][
        "quantity_on_hand"
    ]
    assert after == before - 4

    movements = inventory_service.get_stock_movements(
        product_id="PRD-1009", movement_type="stock_adjustment", limit=200
    )["movements"]
    assert any(
        row["quantity_change"] == -4 and row["reference"].startswith("ADJ-")
        for row in movements
    )


def test_stock_adjustment_can_be_edited_before_execution(inventory_service):
    before = inventory_service.get_stock("PRD-1009", "WH-001")["stock"][0][
        "quantity_on_hand"
    ]
    graph, _ = build(
        inventory_service,
        [
            tool_call(
                "adjust_stock",
                {
                    "product_id": "PRD-1009",
                    "warehouse_id": "WH-001",
                    "quantity_change": -4,
                    "reason": "Damaged units",
                    "performed_by": "EMP-004",
                },
                "call-stock-edit",
            ),
            AIMessage(content="Stock adjusted with the edited quantity."),
        ],
    )
    thread = "thread-stock-edit"
    config = {"configurable": {"thread_id": thread}}
    graph.invoke(
        {"messages": [HumanMessage(content="Reduce stock")]},
        config=config,
    )
    payload = payload_for(graph, thread)

    graph.invoke(
        Command(
            resume={
                "action": "edit",
                "arguments": {
                    "product_id": "PRD-1009",
                    "warehouse_id": "WH-001",
                    "quantity_change": -2,
                    "reason": "Edited by reviewer",
                    "performed_by": "EMP-004",
                },
                "approval_token": payload["approval_token"],
            }
        ),
        config=config,
    )

    after = inventory_service.get_stock("PRD-1009", "WH-001")["stock"][0][
        "quantity_on_hand"
    ]
    assert after == before - 2


def test_stock_adjustment_rejection_leaves_stock_unchanged(inventory_service):
    before = inventory_service.get_stock("PRD-1009", "WH-001")["stock"][0][
        "quantity_on_hand"
    ]
    graph, _ = build(
        inventory_service,
        [
            tool_call(
                "adjust_stock",
                {
                    "product_id": "PRD-1009",
                    "warehouse_id": "WH-001",
                    "quantity_change": -4,
                    "reason": "Damaged units",
                    "performed_by": "EMP-004",
                },
                "call-stock-reject",
            ),
            AIMessage(content="Nothing changed."),
        ],
    )
    thread = "thread-stock-reject"
    config = {"configurable": {"thread_id": thread}}
    graph.invoke(
        {"messages": [HumanMessage(content="Reduce stock")]},
        config=config,
    )
    payload = payload_for(graph, thread)

    graph.invoke(
        Command(
            resume={
                "action": "reject",
                "approval_token": payload["approval_token"],
                "comment": "Count is correct",
            }
        ),
        config=config,
    )

    after = inventory_service.get_stock("PRD-1009", "WH-001")["stock"][0][
        "quantity_on_hand"
    ]
    assert after == before
    tool_messages = [
        message
        for message in graph.get_state(config).values["messages"]
        if isinstance(message, ToolMessage)
    ]
    assert "rejected" in tool_messages[-1].content.lower()
    assert "Count is correct" in tool_messages[-1].content


def test_pending_approval_survives_restart_and_same_thread_resumes(
    inventory_service, tmp_path
):
    config = {"configurable": {"thread_id": "persisted-thread"}}
    manager_first = create_connection(str(tmp_path / "checkpoints.db"))
    saver_first = SqliteSaver(manager_first)
    saver_first.setup()

    graph_first, _ = build(
        inventory_service,
        [
            tool_call(
                "update_product",
                {"product_id": "PRD-1001", "selling_price": 95000},
                "call-persist",
            ),
            AIMessage(content="Updated after restart."),
        ],
        saver_first,
    )
    graph_first.invoke(
        {"messages": [HumanMessage(content="raise price")]}, config=config
    )
    payload = payload_for(graph_first, "persisted-thread")
    assert payload is not None
    assert graph_first.get_state(config).next == ("approval",)
    manager_first.close()

    # Simulate a new process: new connection, new saver, new compiled graph.
    manager_second = create_connection(str(tmp_path / "checkpoints.db"))
    saver_second = SqliteSaver(manager_second)
    saver_second.setup()
    graph_second, _ = build(
        inventory_service,
        [AIMessage(content="Updated after restart.")],
        saver_second,
    )

    assert graph_second.get_state(config).next == ("approval",)
    restored = payload_for(graph_second, "persisted-thread")
    assert restored["tool_call_id"] == "call-persist"
    assert restored["approval_token"] == payload["approval_token"]

    graph_second.invoke(
        Command(
            resume={
                "action": "approve",
                "approval_token": restored["approval_token"],
            }
        ),
        config=config,
    )

    assert price_of(inventory_service) == 95000
    assert graph_second.get_state(config).values["messages"][-1].content == (
        "Updated after restart."
    )

    other = graph_second.get_state({"configurable": {"thread_id": "another-thread"}})
    assert not other.tasks

    manager_second.close()


def test_repeated_resume_does_not_duplicate_the_operation(inventory_service):
    graph, _ = build(
        inventory_service,
        [
            tool_call(
                "record_payment",
                {
                    "invoice_id": "INV-2026-003",
                    "amount": 1000,
                    "method": "cash",
                },
                "call-payment",
            ),
            AIMessage(content="Payment recorded."),
        ],
    )
    thread = "thread-payment"
    config = {"configurable": {"thread_id": thread}}
    graph.invoke({"messages": [HumanMessage(content="record payment")]}, config=config)
    payload = payload_for(graph, thread)

    decision = Command(
        resume={"action": "approve", "approval_token": payload["approval_token"]}
    )
    graph.invoke(decision, config=config)

    invoice = inventory_service.get_invoice("INV-2026-003")["invoice"]
    paid_once = invoice["amount_paid"]
    assert paid_once == 1000

    graph.invoke(decision, config=config)

    invoice = inventory_service.get_invoice("INV-2026-003")["invoice"]
    assert invoice["amount_paid"] == paid_once
    operations = [
        row
        for row in inventory_service.store.snapshot()["operation_log"]
        if row["operation_id"] == f"{thread}:call-payment"
    ]
    assert len(operations) == 1


def test_chat_service_emits_interrupt_and_resumes_with_command():
    class InterruptChatbot:
        def __init__(self):
            self.inputs = []

        def get_state(self, config):
            return SimpleNamespace(values={"messages": []})

        def stream(self, inputs, config, stream_mode, version):
            self.inputs.append(inputs)
            if len(self.inputs) == 1:
                yield {
                    "type": "updates",
                    "data": {
                        "__interrupt__": (
                            SimpleNamespace(
                                id="int-1", value={"tool": "update_product"}
                            ),
                        )
                    },
                }
            else:
                yield {
                    "type": "messages",
                    "data": (
                        SimpleNamespace(content="Resumed."),
                        {"langgraph_node": "chat_node"},
                    ),
                }

    chatbot = InterruptChatbot()
    service = ChatService(
        chatbot,
        FakeThreadService(),
        FakeTitleService(),
        "You are helpful.",
    )

    first = list(service.stream_turn("thread-1", "raise price"))
    interrupts = [event for event in first if event.type == "interrupt"]
    assert interrupts == [
        TurnEvent(
            type="interrupt",
            name="approval",
            payload={"tool": "update_product"},
        )
    ]

    resumed = list(service.resume_turn("thread-1", {"action": "approve"}))
    assert isinstance(chatbot.inputs[1], Command)
    assert [event.content for event in resumed if event.type == "token"] == ["Resumed."]
    assert resumed[-1].type == "done"


def test_chat_service_reads_a_pending_interrupt_from_state():
    class PendingChatbot:
        def get_state(self, config):
            return SimpleNamespace(
                values={"messages": []},
                tasks=(
                    SimpleNamespace(
                        interrupts=(
                            SimpleNamespace(id="int-7", value={"tool": "x"}),
                        )
                    ),
                ),
            )

    service = ChatService(
        PendingChatbot(),
        FakeThreadService(),
        FakeTitleService(),
        "You are helpful.",
    )

    assert service.get_pending_interrupt("thread-1") == {
        "interrupt_id": "int-7",
        "value": {"tool": "x"},
    }
