"""Business rules: catalogue, stock, sales, invoices, payments, procurement."""

import pytest

from agentic_chatbot.inventory.service import InventoryError, InventoryService


def available(service, product_id, warehouse_id=""):
    return service.check_product_availability(product_id, warehouse_id)[
        "available_quantity"
    ]


def test_list_get_and_search_products(inventory_service):
    listing = inventory_service.list_products(limit=100)
    assert listing["count"] == 36
    assert listing["products"][0]["category_name"]
    assert "available_quantity" in listing["products"][0]

    product = inventory_service.get_product("LAP-BIZ-14-001")["product"]
    assert product["product_id"] == "PRD-1001"
    assert product["selling_price"] == 89500

    results = inventory_service.search_products("laptop")
    assert results["count"] >= 2
    assert any(row["product_id"] == "PRD-1001" for row in results["products"])

    category = inventory_service.list_products(category_id="CAT-002", limit=100)
    assert category["count"] >= 5


def test_create_product_and_reject_duplicate_sku(inventory_service):
    result = inventory_service.create_product(
        sku="LAP-NEW-99-099",
        name="Test Laptop",
        category_id="CAT-002",
        unit_id="UNT-001",
        supplier_id="SUP-001",
        purchase_price=50000,
        selling_price=65000,
        description="A product created by a test.",
        reorder_level=5,
    )

    assert result["product"]["product_id"] == "PRD-1037"
    assert result["product"]["is_active"] is True

    with pytest.raises(InventoryError, match="already exists"):
        inventory_service.create_product(
            sku="LAP-BIZ-14-001",
            name="Duplicate SKU",
            category_id="CAT-002",
            unit_id="UNT-001",
            supplier_id="SUP-001",
            purchase_price=1,
            selling_price=2,
            description="Duplicate.",
        )

    with pytest.raises(InventoryError, match="below purchase_price"):
        inventory_service.create_product(
            sku="BAD-PRICE-01",
            name="Bad Price",
            category_id="CAT-002",
            unit_id="UNT-001",
            supplier_id="SUP-001",
            purchase_price=50000,
            selling_price=40000,
            description="Invalid price.",
        )


def test_update_product_price_and_deactivate_preserves_history(inventory_service):
    updated = inventory_service.update_product("PRD-1001", selling_price=95000)
    assert updated["product"]["selling_price"] == 95000
    assert updated["previous"]["selling_price"] == 89500

    deactivated = inventory_service.deactivate_product(
        "PRD-1005", "Discontinued model"
    )
    assert deactivated["product"]["is_active"] is False

    sale = inventory_service.get_sale("SALE-2026-015")
    assert any(item["product_id"] == "PRD-1005" for item in sale["items"])


def test_stock_availability_and_low_stock(inventory_service):
    assert available(inventory_service, "PRD-1001") == 22
    assert available(inventory_service, "PRD-1001", "WH-001") == 14

    availability = inventory_service.check_product_availability("PRD-1019")
    assert availability["available_quantity"] == 0
    assert availability["is_available"] is False

    low = inventory_service.check_low_stock()
    ids = {row["product_id"] for row in low["low_stock"]}
    assert {"PRD-1019", "PRD-1014", "PRD-1028", "PRD-1033"} <= ids
    assert all(
        row["available_quantity"] <= row["reorder_level"]
        for row in low["low_stock"]
    )


def test_adjust_stock_updates_quantity_and_writes_movement(inventory_service):
    result = inventory_service.adjust_stock(
        "PRD-1002", "WH-001", -3, "Damaged during handling", "EMP-004"
    )

    assert result["previous_on_hand"] == 7
    assert result["new_on_hand"] == 4
    assert result["movement"]["movement_type"] == "stock_adjustment"
    assert result["movement"]["quantity_change"] == -3

    with pytest.raises(InventoryError, match="must not be zero"):
        inventory_service.adjust_stock("PRD-1002", "WH-001", 0, "No change", "EMP-004")

    with pytest.raises(InventoryError, match="negative"):
        inventory_service.adjust_stock(
            "PRD-1028", "WH-001", -5, "Too much", "EMP-004"
        )


def test_transfer_stock_moves_between_warehouses(inventory_service):
    before_source = inventory_service.get_stock("PRD-1008", "WH-001")["stock"][0]
    before_destination = inventory_service.get_stock("PRD-1008", "WH-003")["stock"][0]

    result = inventory_service.transfer_stock(
        "PRD-1008", "WH-001", "WH-003", 2, "EMP-004", "Rebalance"
    )

    assert result["quantity"] == 2
    after_source = inventory_service.get_stock("PRD-1008", "WH-001")["stock"][0]
    after_destination = inventory_service.get_stock("PRD-1008", "WH-003")["stock"][0]
    assert after_source["quantity_on_hand"] == before_source["quantity_on_hand"] - 2
    assert (
        after_destination["quantity_on_hand"]
        == before_destination["quantity_on_hand"] + 2
    )
    assert {row["movement_type"] for row in result["movements"]} == {
        "transfer_out",
        "transfer_in",
    }


def test_sales_totals_and_line_items(inventory_service):
    sale = inventory_service.get_sale("SALE-2026-001")

    assert sale["sale"]["subtotal"] == 93900
    assert sale["sale"]["discount"] == 0
    assert sale["sale"]["tax"] == 4695
    assert sale["sale"]["total"] == 98595
    assert sum(item["line_total"] for item in sale["items"]) == 93900


def test_invoice_balance_and_payment_flow(inventory_service):
    invoice = inventory_service.get_invoice("INV-2026-002")["invoice"]
    assert invoice["total"] == 80588
    assert invoice["amount_paid"] == 50000
    assert invoice["balance_due"] == 30588

    payment = inventory_service.record_payment(
        "INV-2026-002", 30588, "bank_transfer", "RCPT-TEST-1"
    )
    assert payment["invoice"]["status"] == "paid"
    assert payment["invoice"]["balance_due"] == 0
    assert payment["customer_outstanding_balance"] == 0

    with pytest.raises(InventoryError, match="not open for payment"):
        inventory_service.record_payment(
            "INV-2026-002", 1, "cash", "RCPT-TEST-2"
        )

    with pytest.raises(InventoryError, match="exceeds the outstanding balance"):
        inventory_service.record_payment("INV-2026-003", 999999, "cash")


def test_credit_limit_cannot_drop_below_outstanding_balance(inventory_service):
    balance = inventory_service.get_customer_balance("CUS-004")
    assert balance["outstanding_balance"] == 128100

    with pytest.raises(InventoryError, match="below the customer's outstanding"):
        inventory_service.update_customer("CUS-004", credit_limit=100000)


def test_create_confirm_sale_deducts_stock(inventory_service):
    before = available(inventory_service, "PRD-1001", "WH-001")

    created = inventory_service.create_sale(
        customer_id="CUS-001",
        sales_employee_id="EMP-001",
        warehouse_id="WH-001",
        items=[{"product_id": "PRD-1001", "quantity": 1}],
    )
    sale_id = created["sale"]["sale_id"]
    assert created["sale"]["status"] == "pending_approval"
    assert created["sale"]["subtotal"] == 89500
    assert available(inventory_service, "PRD-1001", "WH-001") == before

    confirmed = inventory_service.update_sale(sale_id, "confirmed")
    assert confirmed["sale"]["status"] == "confirmed"
    assert available(inventory_service, "PRD-1001", "WH-001") == before - 1

    movements = inventory_service.get_stock_movements(
        product_id="PRD-1001", movement_type="sale", limit=200
    )
    assert any(row["reference"] == sale_id for row in movements["movements"])


def test_invoice_requires_confirmed_sale(inventory_service):
    with pytest.raises(InventoryError, match="Only a confirmed sale"):
        inventory_service.create_invoice("SALE-2026-009")

    invoice = inventory_service.create_invoice("SALE-2026-003")
    assert invoice["invoice"]["status"] == "unpaid"
    assert invoice["invoice"]["total"] == inventory_service.get_sale(
        "SALE-2026-003"
    )["sale"]["total"]


def test_purchase_order_creation_approval_and_receipt(inventory_service):
    before = inventory_service.get_stock("PRD-1015", "WH-001")["stock"][0][
        "quantity_on_hand"
    ]

    created = inventory_service.create_purchase_order(
        supplier_id="SUP-003",
        warehouse_id="WH-001",
        items=[{"product_id": "PRD-1015", "quantity": 10}],
        created_by="EMP-007",
    )
    order_id = created["purchase_order"]["purchase_order_id"]
    assert created["purchase_order"]["status"] == "pending_approval"
    assert created["purchase_order"]["total"] == 53000

    approved = inventory_service.update_purchase_order(order_id, "approved")
    assert approved["purchase_order"]["status"] == "approved"

    received = inventory_service.receive_purchase_order(order_id)
    assert received["purchase_order"]["status"] == "received"

    after = inventory_service.get_stock("PRD-1015", "WH-001")["stock"][0][
        "quantity_on_hand"
    ]
    assert after == before + 10
    assert any(
        row["reference"] == order_id
        for row in received["received_items"]
    )


def test_invalid_purchase_order_transition_is_rejected(inventory_service):
    with pytest.raises(InventoryError, match="Cannot move purchase order"):
        inventory_service.update_purchase_order("PO-2026-009", "approved")

    with pytest.raises(InventoryError, match="Use receive_purchase_order"):
        inventory_service.update_purchase_order("PO-2026-005", "received")


def test_process_return_restocks_and_records_refund(inventory_service):
    before = inventory_service.get_stock("PRD-1013", "WH-001")["stock"][0][
        "quantity_on_hand"
    ]

    result = inventory_service.process_return("RET-2026-001", "approve", "EMP-006")

    assert result["return"]["status"] == "processed"
    assert result["return"]["approved_by"] == "EMP-006"
    assert result["refund_amount"] == 6200
    assert result["movement"]["movement_type"] == "sales_return"

    after = inventory_service.get_stock("PRD-1013", "WH-001")["stock"][0][
        "quantity_on_hand"
    ]
    assert after == before + 1


def test_return_quantity_cannot_exceed_sold_quantity(inventory_service):
    with pytest.raises(InventoryError, match="remain returnable"):
        inventory_service.create_return_request(
            "SALE-2026-005", "PRD-1013", 99, "Too many"
        )


def test_operation_id_makes_mutations_idempotent(inventory_service):
    first = inventory_service.update_product(
        "PRD-1001", selling_price=95000, operation_id="operation-1"
    )
    second = inventory_service.update_product(
        "PRD-1001", selling_price=1, operation_id="operation-1"
    )

    assert first["product"]["selling_price"] == 95000
    assert second["product"]["selling_price"] == 95000
    assert inventory_service.get_product("PRD-1001")["product"]["selling_price"] == 95000
    operations = [
        row
        for row in inventory_service.store.snapshot()["operation_log"]
        if row["operation_id"] == "operation-1"
    ]
    assert len(operations) == 1


def test_financial_summary_reports_core_figures(inventory_service):
    summary = inventory_service.get_financial_summary()

    assert summary["currency"] == "BDT"
    assert summary["accounts_receivable"] > 0
    assert summary["accounts_payable"] > 0
    assert summary["inventory_value_at_cost"] > 0
    assert summary["sales_revenue"] > 0
    assert summary["approved_expenses"] > 0


def test_hitl_decision_is_written_to_the_audit_log(inventory_service):
    payload = {
        "tool": "update_product",
        "operation_id": "thread:call",
        "arguments": {"product_id": "PRD-1001", "selling_price": 95000},
    }
    result = inventory_service.record_hitl_decision(
        payload,
        {"action": "reject", "comment": "Not authorised"},
        "rejected",
    )

    assert result["audit"]["action"] == "approval_rejected"
    assert result["audit"]["actor_id"] == "HUMAN_OPERATOR"
    assert result["audit"]["result"] == "rejected"


def test_audit_records_the_configured_operator(inventory_service):
    payload = {
        "tool": "update_product",
        "operation_id": "thread:call-operator",
        "arguments": {"product_id": "PRD-1001", "selling_price": 95000},
    }

    result = inventory_service.record_hitl_decision(
        payload,
        {"action": "approve"},
        "success",
        actor_id="EMP-006",
    )

    assert result["audit"]["actor_id"] == "EMP-006"
    assert result["audit"]["new_value"]["reviewed_by"] == "EMP-006"


def test_unknown_operator_falls_back_to_human_operator(inventory_service):
    result = inventory_service.record_hitl_decision(
        {
            "tool": "update_product",
            "operation_id": "thread:call-unknown",
            "arguments": {},
        },
        {"action": "approve"},
        "success",
        actor_id="EMP-999",
    )

    assert result["audit"]["actor_id"] == "HUMAN_OPERATOR"


def test_operation_log_retention_keeps_the_latest_entries(inventory_store):
    service = InventoryService(inventory_store, operation_log_limit=2)

    for index in range(3):
        service.update_product(
            "PRD-1001",
            selling_price=90000 + index,
            operation_id=f"retention-{index}",
        )

    rows = inventory_store.snapshot()["operation_log"]
    assert len(rows) == 2
    assert [row["operation_id"] for row in rows] == ["retention-1", "retention-2"]


def test_audit_log_retention_keeps_the_latest_entries(inventory_store):
    service = InventoryService(inventory_store, audit_log_limit=2)

    for index in range(3):
        service.record_hitl_decision(
            {
                "tool": "update_product",
                "operation_id": f"audit-{index}",
                "arguments": {},
            },
            {"action": "approve"},
            "success",
            actor_id="EMP-006",
        )

    rows = inventory_store.snapshot()["audit_log"]
    assert len(rows) == 2
    assert rows[-1]["resource_id"] == "audit-2"


def test_describe_employee_returns_a_reviewer_label(inventory_service):
    assert inventory_service.describe_employee("EMP-006") == (
        "Shirin Sultana (EMP-006)"
    )
    assert inventory_service.describe_employee("EMP-999") == "HUMAN_OPERATOR"
