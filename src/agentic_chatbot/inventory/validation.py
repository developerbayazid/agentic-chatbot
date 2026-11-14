"""Integrity validation for the inventory demo dataset.

The validator is deliberately strict and never repairs data. It is called on
load and again inside every write transaction, so an inconsistent dataset can
neither start the application nor be persisted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

COLLECTIONS: tuple[str, ...] = (
    "categories",
    "units",
    "products",
    "suppliers",
    "customers",
    "employees",
    "warehouses",
    "stock",
    "stock_movements",
    "sales",
    "sale_items",
    "invoices",
    "payments",
    "purchase_orders",
    "purchase_order_items",
    "accounts",
    "expenses",
    "journal_entries",
    "sales_targets",
    "returns",
    "approvals",
    "audit_log",
    "operation_log",
)

REQUIRED_METADATA: tuple[str, ...] = (
    "dataset_name",
    "version",
    "description",
    "currency",
    "date_format",
    "timezone",
    "last_updated",
    "fictional_notice",
)

CURRENCY = "BDT"
DATE_FORMAT = "YYYY-MM-DD"

SALE_STATUSES = {
    "draft",
    "pending_approval",
    "confirmed",
    "invoiced",
    "partially_paid",
    "paid",
    "cancelled",
}

INVOICE_STATUSES = {"draft", "unpaid", "partially_paid", "paid", "overdue", "cancelled"}
PAYMENT_STATUSES = {"completed", "pending", "failed", "refunded"}
PAYMENT_METHODS = {"cash", "bank_transfer", "mobile_banking", "card"}
PURCHASE_ORDER_STATUSES = {
    "draft",
    "pending_approval",
    "approved",
    "rejected",
    "ordered",
    "partially_received",
    "received",
    "cancelled",
}
MOVEMENT_TYPES = {
    "purchase_receipt",
    "sale",
    "stock_adjustment",
    "transfer_in",
    "transfer_out",
    "sales_return",
}
ACCOUNT_TYPES = {"Asset", "Liability", "Equity", "Revenue", "Expense"}
NORMAL_BALANCES = {"debit", "credit"}
EXPENSE_STATUSES = {"draft", "pending_approval", "approved", "rejected", "paid"}
JOURNAL_STATUSES = {"draft", "posted", "void"}
RETURN_STATUSES = {"pending_review", "approved", "rejected", "processed"}
APPROVAL_STATUSES = {"pending", "approved", "rejected"}
AUDIT_RESULTS = {"success", "rejected", "failed"}
CUSTOMER_TYPES = {"individual", "business"}
PSEUDO_ACTORS = {"SYSTEM", "AI_AGENT", "HUMAN_OPERATOR"}

RESOURCE_COLLECTIONS = {
    "purchase_order": "purchase_orders",
    "expense": "expenses",
    "sale": "sales",
    "return": "returns",
    "stock_movement": "stock_movements",
    "product": "products",
    "invoice": "invoices",
    "payment": "payments",
}

_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@dataclass
class ValidationReport:
    """Collected errors and warnings. ``ok`` is false when any error exists."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, message: str) -> None:
        self.errors.append(message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }

    def summary(self, limit: int = 25) -> str:
        lines = [f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"]
        lines.extend(f"- {message}" for message in self.errors[:limit])
        if len(self.errors) > limit:
            lines.append(f"- ...and {len(self.errors) - limit} more error(s)")
        return "\n".join(lines)


class DatasetValidationError(ValueError):
    """Raised when a dataset fails validation and must not be persisted."""

    def __init__(self, report: ValidationReport):
        self.report = report
        super().__init__(f"Invalid inventory dataset:\n{report.summary()}")


def validate_dataset(data: Any) -> ValidationReport:
    """Validate the whole dataset and return every problem found."""
    report = ValidationReport()

    if not isinstance(data, dict):
        report.add("Dataset root must be a JSON object.")
        return report

    _validate_metadata(data, report)

    collections: dict[str, list[dict]] = {}
    for name in COLLECTIONS:
        value = data.get(name)
        if value is None:
            report.add(f"Missing required collection: {name}")
            collections[name] = []
        elif not isinstance(value, list):
            report.add(f"Collection {name} must be a list.")
            collections[name] = []
        else:
            collections[name] = [row for row in value if isinstance(row, dict)]
            if len(collections[name]) != len(value):
                report.add(f"Collection {name} contains non-object entries.")

    ids = {
        name: _validate_ids(collections[name], _ID_FIELD[name], name, report)
        for name in COLLECTIONS
        if name in _ID_FIELD
    }

    _validate_categories(collections["categories"], ids, report)
    _validate_units(collections["units"], report)
    _validate_employees(collections["employees"], ids, report)
    _validate_warehouses(collections["warehouses"], ids, report)
    _validate_suppliers(collections["suppliers"], report)
    _validate_customers(collections["customers"], report)
    _validate_products(collections["products"], ids, report)
    _validate_stock(collections["stock"], ids, report)
    _validate_movements(collections["stock_movements"], ids, report)
    _validate_sales(collections, ids, report)
    _validate_invoices(collections, ids, report)
    _validate_payments(collections, ids, report)
    _validate_purchase_orders(collections, ids, report)
    _validate_accounts(collections["accounts"], ids, report)
    _validate_expenses(collections["expenses"], ids, report)
    _validate_journals(collections["journal_entries"], ids, report)
    _validate_targets(collections["sales_targets"], ids, report)
    _validate_returns(collections, ids, report)
    _validate_approvals(collections, ids, report)
    _validate_audit(collections["audit_log"], ids, report)
    _validate_operation_log(collections["operation_log"], report)
    _validate_customer_balances(collections, report)
    _validate_dates(collections, report)

    return report


# --- helpers ----------------------------------------------------------------


_ID_FIELD = {
    "categories": "category_id",
    "units": "unit_id",
    "products": "product_id",
    "suppliers": "supplier_id",
    "customers": "customer_id",
    "employees": "employee_id",
    "warehouses": "warehouse_id",
    "stock": "stock_id",
    "stock_movements": "movement_id",
    "sales": "sale_id",
    "sale_items": "sale_item_id",
    "invoices": "invoice_id",
    "payments": "payment_id",
    "purchase_orders": "purchase_order_id",
    "purchase_order_items": "po_item_id",
    "accounts": "account_id",
    "expenses": "expense_id",
    "journal_entries": "journal_entry_id",
    "sales_targets": "target_id",
    "returns": "return_id",
    "approvals": "approval_id",
    "audit_log": "audit_id",
    "operation_log": "operation_id",
}


def _validate_ids(
    rows: list[dict], field_name: str, collection: str, report: ValidationReport
) -> set[str]:
    seen: set[str] = set()
    for row in rows:
        value = row.get(field_name)
        if not isinstance(value, str) or not value.strip():
            report.add(f"{collection}: missing or invalid {field_name}.")
            continue
        if value in seen:
            report.add(f"{collection}: duplicate {field_name} {value!r}.")
        seen.add(value)
    return seen


def _ref(
    report: ValidationReport,
    where: str,
    field_name: str,
    value: Any,
    valid: set[str],
    *,
    allow_empty: bool = False,
) -> bool:
    if value in (None, "") and allow_empty:
        return True
    if value not in valid:
        report.add(f"{where}: {field_name}={value!r} does not reference an existing record.")
        return False
    return True


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _money(value: Any) -> bool:
    return _number(value) and value >= 0


def _is_date(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _validate_metadata(data: dict, report: ValidationReport) -> None:
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        report.add("Missing or invalid metadata object.")
        return
    for key in REQUIRED_METADATA:
        if not metadata.get(key):
            report.add(f"metadata: missing {key}.")
    if metadata.get("currency") not in (None, CURRENCY):
        report.add(f"metadata: currency must be {CURRENCY}.")
    if metadata.get("date_format") not in (None, DATE_FORMAT):
        report.add(f"metadata: date_format must be {DATE_FORMAT}.")
    if metadata.get("timezone") not in (None, "Asia/Dhaka"):
        report.add("metadata: timezone must be Asia/Dhaka.")
    if metadata.get("last_updated") and not _is_timestamp(metadata["last_updated"]):
        report.add("metadata: last_updated must be an ISO 8601 timestamp.")


def _validate_categories(rows: list[dict], ids: dict[str, set[str]], report: ValidationReport) -> None:
    category_ids = ids["categories"]
    for row in rows:
        where = f"category {row.get('category_id')}"
        if not row.get("name"):
            report.add(f"{where}: name is required.")
        _ref(report, where, "parent_category_id", row.get("parent_category_id"), category_ids, allow_empty=True)
        if row.get("parent_category_id") == row.get("category_id"):
            report.add(f"{where}: a category cannot be its own parent.")
        if not isinstance(row.get("is_active"), bool):
            report.add(f"{where}: is_active must be a boolean.")

    parents = {
        row.get("category_id"): row.get("parent_category_id")
        for row in rows
        if row.get("parent_category_id")
    }
    for start in parents:
        seen: set[str] = set()
        current = start
        while current in parents:
            if current in seen:
                report.add(f"category {start}: parent chain contains a cycle.")
                break
            seen.add(current)
            current = parents[current]


def _validate_units(rows: list[dict], report: ValidationReport) -> None:
    for row in rows:
        where = f"unit {row.get('unit_id')}"
        if not row.get("name"):
            report.add(f"{where}: name is required.")
        if not row.get("symbol"):
            report.add(f"{where}: symbol is required.")


def _validate_employees(rows: list[dict], ids: dict[str, set[str]], report: ValidationReport) -> None:
    employee_ids = ids["employees"]
    managers: dict[str, str] = {}
    for row in rows:
        where = f"employee {row.get('employee_id')}"
        for field_name in ("name", "role", "department", "email"):
            if not row.get(field_name):
                report.add(f"{where}: {field_name} is required.")
        manager = row.get("manager_id")
        _ref(report, where, "manager_id", manager, employee_ids, allow_empty=True)
        if manager == row.get("employee_id"):
            report.add(f"{where}: an employee cannot manage themselves.")
        elif manager:
            managers[row["employee_id"]] = manager
        if not isinstance(row.get("is_active"), bool):
            report.add(f"{where}: is_active must be a boolean.")

    for start in managers:
        seen: set[str] = set()
        current = start
        while current in managers:
            if current in seen:
                report.add(f"employee {start}: reporting chain contains a cycle.")
                break
            seen.add(current)
            current = managers[current]


def _validate_warehouses(rows: list[dict], ids: dict[str, set[str]], report: ValidationReport) -> None:
    for row in rows:
        where = f"warehouse {row.get('warehouse_id')}"
        for field_name in ("name", "location"):
            if not row.get(field_name):
                report.add(f"{where}: {field_name} is required.")
        _ref(report, where, "manager_employee_id", row.get("manager_employee_id"), ids["employees"])
        if not isinstance(row.get("is_active"), bool):
            report.add(f"{where}: is_active must be a boolean.")


def _validate_suppliers(rows: list[dict], report: ValidationReport) -> None:
    for row in rows:
        where = f"supplier {row.get('supplier_id')}"
        for field_name in ("name", "contact_person", "email", "phone", "address"):
            if not row.get(field_name):
                report.add(f"{where}: {field_name} is required.")
        if not _number(row.get("payment_terms_days")) or row.get("payment_terms_days") < 0:
            report.add(f"{where}: payment_terms_days must be a non-negative number.")
        if not _money(row.get("outstanding_balance")):
            report.add(f"{where}: outstanding_balance must be non-negative.")
        if not isinstance(row.get("is_active"), bool):
            report.add(f"{where}: is_active must be a boolean.")


def _validate_customers(rows: list[dict], report: ValidationReport) -> None:
    for row in rows:
        where = f"customer {row.get('customer_id')}"
        for field_name in ("name", "email", "phone", "billing_address", "shipping_address"):
            if not row.get(field_name):
                report.add(f"{where}: {field_name} is required.")
        if row.get("customer_type") not in CUSTOMER_TYPES:
            report.add(f"{where}: customer_type must be one of {sorted(CUSTOMER_TYPES)}.")
        if not _money(row.get("credit_limit")):
            report.add(f"{where}: credit_limit must be non-negative.")
        if not _money(row.get("outstanding_balance")):
            report.add(f"{where}: outstanding_balance must be non-negative.")
        if _money(row.get("credit_limit")) and _money(row.get("outstanding_balance")):
            if row["outstanding_balance"] > row["credit_limit"]:
                report.add(f"{where}: outstanding_balance exceeds credit_limit.")
        if not isinstance(row.get("is_active"), bool):
            report.add(f"{where}: is_active must be a boolean.")


def _validate_products(rows: list[dict], ids: dict[str, set[str]], report: ValidationReport) -> None:
    skus: set[str] = set()
    for row in rows:
        where = f"product {row.get('product_id')}"
        if not row.get("name") or not row.get("description"):
            report.add(f"{where}: name and description are required.")
        sku = row.get("sku")
        if not sku:
            report.add(f"{where}: sku is required.")
        elif sku in skus:
            report.add(f"{where}: duplicate sku {sku!r}.")
        else:
            skus.add(sku)
        _ref(report, where, "category_id", row.get("category_id"), ids["categories"])
        _ref(report, where, "unit_id", row.get("unit_id"), ids["units"])
        _ref(report, where, "supplier_id", row.get("supplier_id"), ids["suppliers"])
        for field_name in ("purchase_price", "selling_price", "reorder_level"):
            if not _money(row.get(field_name)):
                report.add(f"{where}: {field_name} must be non-negative.")
        if _money(row.get("purchase_price")) and _money(row.get("selling_price")):
            if row["selling_price"] < row["purchase_price"]:
                report.add(f"{where}: selling_price is below purchase_price.")
        if not row.get("barcode"):
            report.add(f"{where}: barcode is required.")
        if not isinstance(row.get("is_active"), bool):
            report.add(f"{where}: is_active must be a boolean.")
        if not _is_timestamp(row.get("created_at")) or not _is_timestamp(row.get("updated_at")):
            report.add(f"{where}: created_at and updated_at must be timestamps.")


def _validate_stock(rows: list[dict], ids: dict[str, set[str]], report: ValidationReport) -> None:
    pairs: set[tuple[str, str]] = set()
    for row in rows:
        where = f"stock {row.get('stock_id')}"
        product_ok = _ref(report, where, "product_id", row.get("product_id"), ids["products"])
        warehouse_ok = _ref(report, where, "warehouse_id", row.get("warehouse_id"), ids["warehouses"])
        if product_ok and warehouse_ok:
            pair = (row["product_id"], row["warehouse_id"])
            if pair in pairs:
                report.add(f"{where}: duplicate stock row for {pair}.")
            pairs.add(pair)
        on_hand = row.get("quantity_on_hand")
        reserved = row.get("quantity_reserved")
        if not _number(on_hand) or on_hand < 0:
            report.add(f"{where}: quantity_on_hand must be non-negative.")
        if not _number(reserved) or reserved < 0:
            report.add(f"{where}: quantity_reserved must be non-negative.")
        if _number(on_hand) and _number(reserved):
            if reserved > on_hand:
                report.add(f"{where}: reserved quantity exceeds on-hand quantity.")
            if on_hand - reserved < 0:
                report.add(f"{where}: available quantity is negative.")
        if not _is_timestamp(row.get("updated_at")):
            report.add(f"{where}: updated_at must be a timestamp.")


def _validate_movements(rows: list[dict], ids: dict[str, set[str]], report: ValidationReport) -> None:
    for row in rows:
        where = f"movement {row.get('movement_id')}"
        _ref(report, where, "product_id", row.get("product_id"), ids["products"])
        _ref(report, where, "warehouse_id", row.get("warehouse_id"), ids["warehouses"])
        _ref(report, where, "performed_by", row.get("performed_by"), ids["employees"])
        movement_type = row.get("movement_type")
        if movement_type not in MOVEMENT_TYPES:
            report.add(f"{where}: invalid movement_type {movement_type!r}.")
        quantity = row.get("quantity_change")
        if not _number(quantity) or quantity == 0:
            report.add(f"{where}: quantity_change must be a non-zero number.")
        if not row.get("reference"):
            report.add(f"{where}: reference is required.")
        if not _is_date(row.get("movement_date")):
            report.add(f"{where}: movement_date must use YYYY-MM-DD.")
        reference = row.get("reference")
        if movement_type == "sale":
            _ref(report, where, "reference", reference, ids["sales"])
        elif movement_type == "purchase_receipt":
            _ref(report, where, "reference", reference, ids["purchase_orders"])
        elif movement_type == "sales_return":
            _ref(report, where, "reference", reference, ids["returns"])


def _validate_sales(collections: dict[str, list[dict]], ids: dict[str, set[str]], report: ValidationReport) -> None:
    items_by_sale: dict[str, list[dict]] = {}
    for item in collections["sale_items"]:
        items_by_sale.setdefault(item.get("sale_id"), []).append(item)
        where = f"sale item {item.get('sale_item_id')}"
        _ref(report, where, "sale_id", item.get("sale_id"), ids["sales"])
        _ref(report, where, "product_id", item.get("product_id"), ids["products"])
        if not _number(item.get("quantity")) or item["quantity"] <= 0:
            report.add(f"{where}: quantity must be a positive number.")
        if not _money(item.get("unit_price")):
            report.add(f"{where}: unit_price must be non-negative.")
        if _number(item.get("quantity")) and _money(item.get("unit_price")):
            if item.get("line_total") != item["quantity"] * item["unit_price"]:
                report.add(f"{where}: line_total must equal quantity * unit_price.")

    for sale in collections["sales"]:
        sale_id = sale.get("sale_id")
        where = f"sale {sale_id}"
        _ref(report, where, "customer_id", sale.get("customer_id"), ids["customers"])
        _ref(report, where, "sales_employee_id", sale.get("sales_employee_id"), ids["employees"])
        _ref(report, where, "warehouse_id", sale.get("warehouse_id"), ids["warehouses"])
        if sale.get("status") not in SALE_STATUSES:
            report.add(f"{where}: invalid status {sale.get('status')!r}.")
        if sale.get("currency") != CURRENCY:
            report.add(f"{where}: currency must be {CURRENCY}.")
        if not _is_date(sale.get("sale_date")):
            report.add(f"{where}: sale_date must use YYYY-MM-DD.")
        items = items_by_sale.get(sale_id, [])
        if not items:
            report.add(f"{where}: has no sale items.")
            continue
        item_sum = sum(item.get("line_total", 0) for item in items)
        subtotal = sale.get("subtotal")
        discount = sale.get("discount")
        tax = sale.get("tax")
        total = sale.get("total")
        for field_name, value in (("subtotal", subtotal), ("discount", discount), ("tax", tax), ("total", total)):
            if not _money(value):
                report.add(f"{where}: {field_name} must be non-negative.")
        if _money(subtotal) and subtotal != item_sum:
            report.add(f"{where}: subtotal {subtotal} does not equal sale items total {item_sum}.")
        if _money(subtotal) and _money(discount):
            if discount > subtotal:
                report.add(f"{where}: discount exceeds subtotal.")
            if _money(tax) and _money(total):
                expected = subtotal - discount + tax
                if total != expected:
                    report.add(f"{where}: total {total} does not equal subtotal - discount + tax ({expected}).")


def _validate_invoices(collections: dict[str, list[dict]], ids: dict[str, set[str]], report: ValidationReport) -> None:
    sales = {row.get("sale_id"): row for row in collections["sales"]}
    payments_by_invoice: dict[str, float] = {}
    for payment in collections["payments"]:
        if payment.get("status") == "completed":
            invoice_id = payment.get("invoice_id")
            payments_by_invoice[invoice_id] = payments_by_invoice.get(invoice_id, 0) + payment.get("amount", 0)

    for invoice in collections["invoices"]:
        invoice_id = invoice.get("invoice_id")
        where = f"invoice {invoice_id}"
        _ref(report, where, "invoice_id", invoice_id, ids["invoices"])
        _ref(report, where, "sale_id", invoice.get("sale_id"), ids["sales"])
        customer_ok = _ref(report, where, "customer_id", invoice.get("customer_id"), ids["customers"])
        sale = sales.get(invoice.get("sale_id"))
        if sale is not None:
            if customer_ok and sale.get("customer_id") != invoice.get("customer_id"):
                report.add(f"{where}: customer does not match the related sale.")
            if invoice.get("total") != sale.get("total"):
                report.add(f"{where}: total {invoice.get('total')} does not match sale total {sale.get('total')}.")
        status = invoice.get("status")
        if status not in INVOICE_STATUSES:
            report.add(f"{where}: invalid status {status!r}.")
        total = invoice.get("total")
        paid = invoice.get("amount_paid")
        balance = invoice.get("balance_due")
        for field_name, value in (("total", total), ("amount_paid", paid), ("balance_due", balance)):
            if not _money(value):
                report.add(f"{where}: {field_name} must be non-negative.")
        if status == "cancelled":
            if _money(balance) and balance != 0:
                report.add(f"{where}: a cancelled invoice must have zero balance_due.")
            continue
        if _money(total) and _money(paid) and _money(balance):
            if paid + balance != total:
                report.add(f"{where}: amount_paid + balance_due must equal total.")
            if paid > total:
                report.add(f"{where}: amount_paid exceeds total.")
            if status == "paid" and balance != 0:
                report.add(f"{where}: paid invoice must have zero balance_due.")
            if status == "unpaid" and paid != 0:
                report.add(f"{where}: unpaid invoice must have zero amount_paid.")
            if status == "partially_paid" and not (0 < paid < total):
                report.add(f"{where}: partially_paid invoice must have 0 < amount_paid < total.")
            if status == "overdue" and balance <= 0:
                report.add(f"{where}: overdue invoice must have a positive balance.")
        recorded = payments_by_invoice.get(invoice_id, 0)
        if _money(paid) and paid != recorded:
            report.add(f"{where}: amount_paid {paid} does not equal completed payments {recorded}.")
        if status in {"unpaid", "partially_paid", "overdue"} and not _is_date(invoice.get("due_date")):
            report.add(f"{where}: due_date must use YYYY-MM-DD.")
        if not _is_date(invoice.get("issue_date")):
            report.add(f"{where}: issue_date must use YYYY-MM-DD.")


def _validate_payments(collections: dict[str, list[dict]], ids: dict[str, set[str]], report: ValidationReport) -> None:
    invoices = {row.get("invoice_id"): row for row in collections["invoices"]}
    sums: dict[str, float] = {}

    for payment in collections["payments"]:
        invoice_id = payment.get("invoice_id")
        where = f"payment {payment.get('payment_id')}"
        invoice_ok = _ref(report, where, "invoice_id", invoice_id, ids["invoices"])
        customer_ok = _ref(report, where, "customer_id", payment.get("customer_id"), ids["customers"])
        invoice = invoices.get(invoice_id)
        if invoice is not None and customer_ok and invoice.get("customer_id") != payment.get("customer_id"):
            report.add(f"{where}: customer does not match the invoice.")
        amount = payment.get("amount")
        if not _number(amount) or amount <= 0:
            report.add(f"{where}: amount must be positive.")
        if payment.get("method") not in PAYMENT_METHODS:
            report.add(f"{where}: invalid method {payment.get('method')!r}.")
        if payment.get("status") not in PAYMENT_STATUSES:
            report.add(f"{where}: invalid status {payment.get('status')!r}.")
        if not _is_date(payment.get("payment_date")):
            report.add(f"{where}: payment_date must use YYYY-MM-DD.")
        if payment.get("status") == "completed" and invoice_ok:
            sums[invoice_id] = sums.get(invoice_id, 0) + (amount if _number(amount) else 0)

    for invoice_id, total_paid in sums.items():
        invoice = invoices.get(invoice_id)
        if invoice is None:
            continue
        if total_paid > invoice.get("total", 0):
            report.add(f"invoice {invoice_id}: completed payments exceed the invoice total.")


def _validate_purchase_orders(
    collections: dict[str, list[dict]], ids: dict[str, set[str]], report: ValidationReport
) -> None:
    items_by_po: dict[str, list[dict]] = {}
    for item in collections["purchase_order_items"]:
        items_by_po.setdefault(item.get("purchase_order_id"), []).append(item)
        where = f"purchase order item {item.get('po_item_id')}"
        _ref(report, where, "purchase_order_id", item.get("purchase_order_id"), ids["purchase_orders"])
        _ref(report, where, "product_id", item.get("product_id"), ids["products"])
        if not _number(item.get("quantity")) or item["quantity"] <= 0:
            report.add(f"{where}: quantity must be positive.")
        if not _money(item.get("unit_cost")):
            report.add(f"{where}: unit_cost must be non-negative.")
        if _number(item.get("quantity")) and _money(item.get("unit_cost")):
            if item.get("line_total") != item["quantity"] * item["unit_cost"]:
                report.add(f"{where}: line_total must equal quantity * unit_cost.")

    for order in collections["purchase_orders"]:
        order_id = order.get("purchase_order_id")
        where = f"purchase order {order_id}"
        _ref(report, where, "supplier_id", order.get("supplier_id"), ids["suppliers"])
        _ref(report, where, "warehouse_id", order.get("warehouse_id"), ids["warehouses"])
        _ref(report, where, "created_by", order.get("created_by"), ids["employees"])
        if order.get("status") not in PURCHASE_ORDER_STATUSES:
            report.add(f"{where}: invalid status {order.get('status')!r}.")
        if order.get("currency") != CURRENCY:
            report.add(f"{where}: currency must be {CURRENCY}.")
        if not _is_date(order.get("order_date")):
            report.add(f"{where}: order_date must use YYYY-MM-DD.")
        items = items_by_po.get(order_id, [])
        if not items:
            report.add(f"{where}: has no items.")
            continue
        expected = sum(item.get("line_total", 0) for item in items)
        if order.get("total") != expected:
            report.add(f"{where}: total {order.get('total')} does not equal items total {expected}.")


def _validate_accounts(rows: list[dict], ids: dict[str, set[str]], report: ValidationReport) -> None:
    codes: set[str] = set()
    for row in rows:
        where = f"account {row.get('account_id')}"
        if not row.get("account_code"):
            report.add(f"{where}: account_code is required.")
        elif row["account_code"] in codes:
            report.add(f"{where}: duplicate account_code {row['account_code']!r}.")
        else:
            codes.add(row["account_code"])
        if not row.get("name"):
            report.add(f"{where}: name is required.")
        if row.get("account_type") not in ACCOUNT_TYPES:
            report.add(f"{where}: invalid account_type {row.get('account_type')!r}.")
        if row.get("normal_balance") not in NORMAL_BALANCES:
            report.add(f"{where}: invalid normal_balance {row.get('normal_balance')!r}.")
        _ref(report, where, "parent_account_id", row.get("parent_account_id"), ids["accounts"], allow_empty=True)
        if row.get("parent_account_id") == row.get("account_id"):
            report.add(f"{where}: an account cannot be its own parent.")
        if not isinstance(row.get("is_active"), bool):
            report.add(f"{where}: is_active must be a boolean.")


def _validate_expenses(rows: list[dict], ids: dict[str, set[str]], report: ValidationReport) -> None:
    for row in rows:
        where = f"expense {row.get('expense_id')}"
        _ref(report, where, "account_id", row.get("account_id"), ids["accounts"])
        _ref(report, where, "submitted_by", row.get("submitted_by"), ids["employees"])
        approver = row.get("approved_by")
        _ref(report, where, "approved_by", approver, ids["employees"], allow_empty=True)
        if not _number(row.get("amount")) or row.get("amount") <= 0:
            report.add(f"{where}: amount must be positive.")
        if row.get("status") not in EXPENSE_STATUSES:
            report.add(f"{where}: invalid status {row.get('status')!r}.")
        if row.get("status") in {"approved", "paid"} and not approver:
            report.add(f"{where}: approved/paid expenses require approved_by.")
        if row.get("status") == "pending_approval" and approver:
            report.add(f"{where}: pending expenses must not have approved_by.")
        if not _is_date(row.get("expense_date")):
            report.add(f"{where}: expense_date must use YYYY-MM-DD.")


def _validate_journals(rows: list[dict], ids: dict[str, set[str]], report: ValidationReport) -> None:
    for entry in rows:
        entry_id = entry.get("journal_entry_id")
        where = f"journal entry {entry_id}"
        if entry.get("status") not in JOURNAL_STATUSES:
            report.add(f"{where}: invalid status {entry.get('status')!r}.")
        if not entry.get("description"):
            report.add(f"{where}: description is required.")
        if not _is_date(entry.get("entry_date")):
            report.add(f"{where}: entry_date must use YYYY-MM-DD.")
        lines = entry.get("lines")
        if not isinstance(lines, list) or not lines:
            report.add(f"{where}: lines must be a non-empty list.")
            continue
        debit_total = 0
        credit_total = 0
        for index, line in enumerate(lines):
            if not isinstance(line, dict):
                report.add(f"{where}: line {index} must be an object.")
                continue
            _ref(report, where, "account_id", line.get("account_id"), ids["accounts"])
            debit = line.get("debit", 0)
            credit = line.get("credit", 0)
            if not _money(debit) or not _money(credit):
                report.add(f"{where}: line {index} debit/credit must be non-negative.")
                continue
            if debit and credit:
                report.add(f"{where}: line {index} cannot have both debit and credit.")
            debit_total += debit
            credit_total += credit
        if entry.get("status") == "posted":
            if debit_total != credit_total:
                report.add(f"{where}: posted entry is unbalanced ({debit_total} debit vs {credit_total} credit).")
            if debit_total == 0:
                report.add(f"{where}: posted entry has no value.")


def _validate_targets(rows: list[dict], ids: dict[str, set[str]], report: ValidationReport) -> None:
    for row in rows:
        where = f"sales target {row.get('target_id')}"
        _ref(report, where, "employee_id", row.get("employee_id"), ids["employees"])
        if not isinstance(row.get("period"), str) or not _PERIOD.match(row["period"]):
            report.add(f"{where}: period must use YYYY-MM.")
        if not _money(row.get("target_amount")):
            report.add(f"{where}: target_amount must be non-negative.")
        if not _money(row.get("achieved_amount")):
            report.add(f"{where}: achieved_amount must be non-negative.")


def _validate_returns(
    collections: dict[str, list[dict]], ids: dict[str, set[str]], report: ValidationReport
) -> None:
    sales = {row.get("sale_id"): row for row in collections["sales"]}
    sold: dict[tuple[str, str], float] = {}
    for item in collections["sale_items"]:
        key = (item.get("sale_id"), item.get("product_id"))
        sold[key] = sold.get(key, 0) + item.get("quantity", 0)
    unit_prices: dict[tuple[str, str], float] = {}
    for item in collections["sale_items"]:
        unit_prices.setdefault((item.get("sale_id"), item.get("product_id")), item.get("unit_price", 0))

    for row in collections["returns"]:
        where = f"return {row.get('return_id')}"
        sale_ok = _ref(report, where, "sale_id", row.get("sale_id"), ids["sales"])
        customer_ok = _ref(report, where, "customer_id", row.get("customer_id"), ids["customers"])
        _ref(report, where, "product_id", row.get("product_id"), ids["products"])
        sale = sales.get(row.get("sale_id"))
        if sale is not None and customer_ok and sale.get("customer_id") != row.get("customer_id"):
            report.add(f"{where}: customer does not match the related sale.")
        quantity = row.get("quantity")
        if not _number(quantity) or quantity <= 0:
            report.add(f"{where}: quantity must be positive.")
        elif sale_ok:
            key = (row.get("sale_id"), row.get("product_id"))
            if quantity > sold.get(key, 0):
                report.add(f"{where}: quantity exceeds the quantity sold on that sale.")
            refund = row.get("refund_amount")
            line_total = quantity * unit_prices.get(key, 0)
            if _money(refund) and refund > line_total:
                report.add(f"{where}: refund_amount exceeds the sold line value.")
            if not _money(refund):
                report.add(f"{where}: refund_amount must be non-negative.")
        if row.get("status") not in RETURN_STATUSES:
            report.add(f"{where}: invalid status {row.get('status')!r}.")
        _ref(report, where, "approved_by", row.get("approved_by"), ids["employees"], allow_empty=True)
        if row.get("status") in {"approved", "processed"} and not row.get("approved_by"):
            report.add(f"{where}: approved/processed returns require approved_by.")
        if not _is_date(row.get("requested_date")):
            report.add(f"{where}: requested_date must use YYYY-MM-DD.")


def _validate_approvals(
    collections: dict[str, list[dict]], ids: dict[str, set[str]], report: ValidationReport
) -> None:
    for row in collections["approvals"]:
        where = f"approval {row.get('approval_id')}"
        if not row.get("action"):
            report.add(f"{where}: action is required.")
        resource_type = row.get("resource_type")
        if row.get("status") not in APPROVAL_STATUSES:
            report.add(f"{where}: invalid status {row.get('status')!r}.")
        target = RESOURCE_COLLECTIONS.get(resource_type)
        if target is None:
            report.add(f"{where}: unsupported resource_type {resource_type!r}.")
        else:
            _ref(report, where, "resource_id", row.get("resource_id"), ids.get(target, set()))
        _ref(report, where, "requested_by", row.get("requested_by"), ids["employees"])
        _ref(report, where, "assigned_to", row.get("assigned_to"), ids["employees"], allow_empty=True)
        reviewed_by = row.get("reviewed_by")
        _ref(report, where, "reviewed_by", reviewed_by, ids["employees"], allow_empty=True)
        if row.get("status") != "pending":
            if not reviewed_by:
                report.add(f"{where}: a reviewed approval requires reviewed_by.")
            if not row.get("reviewed_at"):
                report.add(f"{where}: a reviewed approval requires reviewed_at.")


def _validate_audit(rows: list[dict], ids: dict[str, set[str]], report: ValidationReport) -> None:
    for row in rows:
        where = f"audit {row.get('audit_id')}"
        actor = row.get("actor_id")
        if actor not in ids["employees"] and actor not in PSEUDO_ACTORS:
            report.add(f"{where}: actor_id={actor!r} is not an employee or a known system actor.")
        if not row.get("action"):
            report.add(f"{where}: action is required.")
        if not row.get("resource_type"):
            report.add(f"{where}: resource_type is required.")
        if row.get("result") not in AUDIT_RESULTS:
            report.add(f"{where}: invalid result {row.get('result')!r}.")
        if not _is_timestamp(row.get("timestamp")):
            report.add(f"{where}: timestamp must be an ISO 8601 timestamp.")


def _validate_operation_log(rows: list[dict], report: ValidationReport) -> None:
    seen: set[str] = set()
    for row in rows:
        operation_id = row.get("operation_id")
        where = f"operation {operation_id}"
        if not operation_id:
            report.add(f"{where}: operation_id is required.")
        elif operation_id in seen:
            report.add(f"{where}: duplicate operation_id.")
        else:
            seen.add(operation_id)
        if not row.get("tool"):
            report.add(f"{where}: tool is required.")
        if not _is_timestamp(row.get("executed_at")):
            report.add(f"{where}: executed_at must be an ISO 8601 timestamp.")


def _validate_customer_balances(collections: dict[str, list[dict]], report: ValidationReport) -> None:
    balances: dict[str, float] = {}
    for invoice in collections["invoices"]:
        if invoice.get("status") in {"unpaid", "partially_paid", "overdue"}:
            customer_id = invoice.get("customer_id")
            balances[customer_id] = balances.get(customer_id, 0) + invoice.get("balance_due", 0)
    for customer in collections["customers"]:
        customer_id = customer.get("customer_id")
        expected = balances.get(customer_id, 0)
        actual = customer.get("outstanding_balance")
        if _money(actual) and actual != expected:
            report.add(
                f"customer {customer_id}: outstanding_balance {actual} does not equal "
                f"open invoice balances {expected}."
            )
        if _money(actual) and _money(customer.get("credit_limit")):
            if actual > customer["credit_limit"]:
                report.add(f"customer {customer_id}: outstanding_balance exceeds credit_limit.")


_DATE_FIELDS = {
    "customers": ("created_at",),
    "employees": ("created_at",),
    "warehouses": ("created_at",),
    "suppliers": ("created_at",),
    "stock_movements": ("movement_date",),
    "sales": ("sale_date",),
    "invoices": ("issue_date", "due_date"),
    "payments": ("payment_date",),
    "purchase_orders": ("order_date", "expected_date"),
    "expenses": ("expense_date",),
    "journal_entries": ("entry_date",),
    "returns": ("requested_date",),
}


def _validate_dates(collections: dict[str, list[dict]], report: ValidationReport) -> None:
    """Validate optional date/timestamp fields that may not exist on every row."""
    for collection, fields in _DATE_FIELDS.items():
        for row in collections.get(collection, []):
            where = f"{collection} {row.get(_ID_FIELD.get(collection, 'id'))}"
            for field_name in fields:
                value = row.get(field_name)
                if value in (None, ""):
                    continue
                if field_name.endswith("_at"):
                    if not _is_timestamp(value):
                        report.add(f"{where}: {field_name} must be an ISO 8601 timestamp.")
                elif not _is_date(value):
                    report.add(f"{where}: {field_name} must use YYYY-MM-DD.")
