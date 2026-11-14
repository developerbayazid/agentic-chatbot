"""Dataset integrity: JSON loading, validation, and atomic persistence."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agentic_chatbot.inventory.data_access import InventoryStore, InventoryStoreError
from agentic_chatbot.inventory.validation import (
    DatasetValidationError,
    validate_dataset,
)

INVENTORY_SEED = (
    Path(__file__).resolve().parents[1]
    / "inventory-data"
    / "inventory"
    / "inventory_data.seed.json"
)
INVENTORY_WORKING = INVENTORY_SEED.parent / "inventory_data.json"


def load() -> dict:
    return json.loads(INVENTORY_SEED.read_text(encoding="utf-8"))


def errors(data: dict) -> list[str]:
    return validate_dataset(data).errors


def assert_error(data: dict, fragment: str) -> None:
    report = validate_dataset(data)
    assert not report.ok
    assert any(fragment in message for message in report.errors), report.errors


def test_checked_in_dataset_is_valid_and_interconnected():
    data = load()
    report = validate_dataset(data)

    assert report.ok, report.summary()
    assert report.errors == []
    assert data["metadata"]["currency"] == "BDT"
    assert data["metadata"]["timezone"] == "Asia/Dhaka"
    assert len(data["categories"]) >= 8
    assert 30 <= len(data["products"]) <= 40
    assert len(data["suppliers"]) >= 8
    assert 15 <= len(data["customers"]) <= 20
    assert len(data["employees"]) == 10
    assert len(data["warehouses"]) == 3
    assert len(data["invoices"]) >= 12
    assert 8 <= len(data["purchase_orders"]) <= 10
    assert any(row["parent_category_id"] for row in data["categories"])
    assert any(row["quantity_on_hand"] == 0 for row in data["stock"])
    assert any(row["status"] == "pending" for row in data["approvals"])


def test_working_dataset_remains_valid_after_live_use():
    if not INVENTORY_WORKING.exists():
        pytest.skip("working dataset is not present")

    report = validate_dataset(
        json.loads(INVENTORY_WORKING.read_text(encoding="utf-8"))
    )
    assert report.ok, report.summary()


def test_missing_collection_is_reported():
    data = load()
    data.pop("products")

    assert_error(data, "Missing required collection: products")


def test_duplicate_primary_ids_are_reported():
    data = load()
    duplicate = copy.deepcopy(data["products"][0])
    data["products"].append(duplicate)

    assert_error(data, "duplicate product_id")


def test_duplicate_skus_are_reported():
    data = load()
    duplicate = copy.deepcopy(data["products"][1])
    duplicate["product_id"] = "PRD-9999"
    data["products"].append(duplicate)

    assert_error(data, "duplicate sku")


def test_invalid_foreign_keys_are_reported():
    data = load()
    data["products"][0]["category_id"] = "CAT-999"
    data["stock"][0]["warehouse_id"] = "WH-999"
    data["sales"][0]["customer_id"] = "CUS-999"

    messages = errors(data)
    assert any("CAT-999" in message for message in messages)
    assert any("WH-999" in message for message in messages)
    assert any("CUS-999" in message for message in messages)


def test_inventory_consistency_is_enforced():
    data = load()
    row = data["stock"][0]
    row["quantity_reserved"] = row["quantity_on_hand"] + 1

    assert_error(data, "reserved quantity exceeds on-hand quantity")

    negative = load()
    negative["stock"][1]["quantity_on_hand"] = -1
    assert_error(negative, "quantity_on_hand must be non-negative")


def test_sale_and_invoice_financial_consistency():
    data = load()
    data["sales"][0]["total"] += 1
    assert_error(data, "does not equal subtotal - discount + tax")

    invoice = load()
    invoice["invoices"][1]["balance_due"] += 1
    assert_error(invoice, "amount_paid + balance_due must equal total")

    payment = load()
    payment["payments"][0]["amount"] = payment["invoices"][0]["total"] * 2
    assert_error(payment, "completed payments exceed the invoice total")


def test_purchase_order_totals_must_match_items():
    data = load()
    data["purchase_orders"][0]["total"] += 1

    assert_error(data, "does not equal items total")


def test_posted_journal_entries_must_balance():
    data = load()
    entry = next(row for row in data["journal_entries"] if row["status"] == "posted")
    entry["lines"][0]["debit"] += 1

    assert_error(data, "posted entry is unbalanced")


def test_customer_balance_must_match_open_invoices():
    data = load()
    customer = next(row for row in data["customers"] if row["outstanding_balance"] > 0)
    customer["outstanding_balance"] += 1

    assert_error(data, "does not equal open invoice balances")


def test_approvals_must_reference_existing_resources():
    data = load()
    data["approvals"][0]["resource_id"] = "PO-9999"

    assert_error(data, "PO-9999")


def test_invalid_json_is_reported_clearly(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ this is not json", encoding="utf-8")

    with pytest.raises(InventoryStoreError, match="not valid JSON"):
        InventoryStore(path)


def test_missing_dataset_raises_a_specific_error(tmp_path):
    with pytest.raises(InventoryStoreError, match="not found"):
        InventoryStore(tmp_path / "missing.json")


def test_transaction_aborts_without_repairing_data(inventory_data_path):
    store = InventoryStore(inventory_data_path)
    original = inventory_data_path.read_text(encoding="utf-8")

    with pytest.raises(DatasetValidationError):
        with store.transaction() as data:
            data["products"][0]["selling_price"] = 1

    assert inventory_data_path.read_text(encoding="utf-8") == original


def test_transaction_persists_valid_changes(inventory_data_path):
    store = InventoryStore(inventory_data_path)

    with store.transaction() as data:
        data["products"][0]["name"] = "Renamed Laptop"

    reloaded = InventoryStore(inventory_data_path)
    assert reloaded.get("products", "product_id", "PRD-1001")["name"] == "Renamed Laptop"
    assert inventory_data_path.read_text(encoding="utf-8").endswith("\n")


def test_next_id_avoids_collisions(inventory_store):
    data = inventory_store.snapshot()

    assert (
        inventory_store.next_id(data, "products", "product_id", "PRD", width=4)
        == "PRD-1037"
    )
    assert (
        inventory_store.next_id(data, "invoices", "invoice_id", "INV-2026", width=3)
        == "INV-2026-014"
    )
    assert (
        inventory_store.next_id(data, "audit_log", "audit_id", "AUD-2026", width=3)
        == "AUD-2026-013"
    )


def test_concurrent_transactions_do_not_lose_updates(inventory_service):
    product_id = "PRD-1002"
    before = inventory_service.get_product(product_id)["product"]["available_quantity"]

    def increment(_):
        return inventory_service.adjust_stock(
            product_id, "WH-001", 1, "Concurrency test", "EMP-004"
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(increment, range(5)))

    after = inventory_service.get_product(product_id)["product"]["available_quantity"]
    assert after == before + 5
