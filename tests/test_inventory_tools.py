"""Inventory tool registration, descriptions, and direct execution."""

import json

from agentic_chatbot.inventory.approvals import SENSITIVE_TOOLS
from agentic_chatbot.inventory.tools import create_inventory_tools

REQUESTED_TOOLS = {
    "list_products",
    "get_product",
    "search_products",
    "create_product",
    "update_product",
    "deactivate_product",
    "list_categories",
    "create_category",
    "update_category",
    "get_stock",
    "check_low_stock",
    "check_product_availability",
    "adjust_stock",
    "transfer_stock",
    "get_stock_movements",
    "list_customers",
    "get_customer",
    "search_customers",
    "create_customer",
    "update_customer",
    "list_suppliers",
    "get_supplier",
    "search_suppliers",
    "list_sales",
    "get_sale",
    "create_sale",
    "update_sale",
    "cancel_sale",
    "get_sales_by_customer",
    "get_sales_by_employee",
    "list_invoices",
    "get_invoice",
    "create_invoice",
    "record_payment",
    "get_outstanding_invoices",
    "get_customer_balance",
    "list_purchase_orders",
    "get_purchase_order",
    "create_purchase_order",
    "update_purchase_order",
    "receive_purchase_order",
    "list_accounts",
    "get_account",
    "list_expenses",
    "create_expense",
    "get_financial_summary",
    "get_sales_summary",
    "create_return_request",
    "get_return",
    "list_returns",
    "process_return",
    "get_pending_approvals",
    "get_approval_details",
    "get_approval_history",
}


def tool_map(service):
    return {tool.name: tool for tool in create_inventory_tools(service)}


def test_every_requested_tool_is_registered(inventory_service):
    tools = tool_map(inventory_service)

    assert set(tools) == REQUESTED_TOOLS
    assert len(tools) == 54


def test_only_mutating_operations_require_approval(inventory_service):
    tools = tool_map(inventory_service)

    assert set(SENSITIVE_TOOLS) <= set(tools)
    assert {
        "update_product",
        "deactivate_product",
        "adjust_stock",
        "record_payment",
        "create_purchase_order",
        "process_return",
    } <= set(SENSITIVE_TOOLS)

    read_only = {
        "list_products",
        "get_product",
        "search_products",
        "check_low_stock",
        "check_product_availability",
        "get_outstanding_invoices",
        "get_customer_balance",
        "get_financial_summary",
        "get_pending_approvals",
    }
    assert read_only.isdisjoint(SENSITIVE_TOOLS)


def test_tool_descriptions_state_when_to_use_them(inventory_service):
    tools = tool_map(inventory_service)

    assert "available" in tools["check_product_availability"].description.lower()
    assert "reorder" in tools["check_low_stock"].description.lower()
    assert "unpaid" in tools["get_outstanding_invoices"].description.lower()
    assert "owe" in tools["get_customer_balance"].description.lower()
    assert "human approval" in tools["update_product"].description.lower()
    assert "soft-delete" in tools["deactivate_product"].description.lower()
    assert "balance" in tools["record_payment"].description.lower()
    assert "helper approval" not in tools["update_product"].description.lower()


def test_read_only_tools_return_json(inventory_service):
    tools = tool_map(inventory_service)

    products = json.loads(tools["list_products"].invoke({"limit": 5}))
    assert products["count"] == 36

    product = json.loads(tools["get_product"].invoke({"product_id": "PRD-1001"}))
    assert product["product"]["sku"] == "LAP-BIZ-14-001"

    availability = json.loads(
        tools["check_product_availability"].invoke({"product_id": "PRD-1019"})
    )
    assert availability["available_quantity"] == 0

    low = json.loads(tools["check_low_stock"].invoke({}))
    assert {"PRD-1019", "PRD-1014"} <= {row["product_id"] for row in low["low_stock"]}

    balance = json.loads(
        tools["get_customer_balance"].invoke({"customer_id": "CUS-004"})
    )
    assert balance["outstanding_balance"] == 128100

    outstanding = json.loads(tools["get_outstanding_invoices"].invoke({}))
    assert outstanding["count"] >= 1
    assert outstanding["total_outstanding"] > 0


def test_tool_errors_are_returned_not_raised(inventory_service):
    tools = tool_map(inventory_service)

    result = tools["get_product"].invoke({"product_id": "PRD-9999"})
    assert result.startswith("Error:")

    result = tools["adjust_stock"].invoke(
        {
            "product_id": "PRD-1028",
            "warehouse_id": "WH-001",
            "quantity_change": -99,
            "reason": "too much",
            "performed_by": "EMP-004",
        },
        {"configurable": {"inventory_operation_id": "op-tool-negative"}},
    )
    assert result.startswith("Error:")


def test_sensitive_tool_uses_the_injected_operation_id(inventory_service):
    tools = tool_map(inventory_service)

    result = json.loads(
        tools["update_product"].invoke(
            {"product_id": "PRD-1001", "selling_price": 95000},
            {"configurable": {"inventory_operation_id": "op-tool-1"}},
        )
    )
    assert result["product"]["selling_price"] == 95000

    operations = [
        row
        for row in inventory_service.store.snapshot()["operation_log"]
        if row["operation_id"] == "op-tool-1"
    ]
    assert len(operations) == 1
    assert operations[0]["tool"] == "update_product"


def test_preview_shows_current_and_proposed_values(inventory_service):
    preview = inventory_service.preview_operation(
        "update_product", {"product_id": "PRD-1001", "selling_price": 95000}
    )
    labels = {label: value for label, value in preview["summary"]}

    assert labels["Product"] == "Latitude Business Laptop 14"
    assert labels["SKU"] == "LAP-BIZ-14-001"
    assert labels["Current Selling Price"] == "BDT 89,500"
    assert labels["Proposed Selling Price"] == "BDT 95,000"
    assert preview["warnings"] == []

    missing = inventory_service.preview_operation(
        "update_product", {"product_id": "PRD-9999", "selling_price": 1}
    )
    assert missing["warnings"]
