"""Inventory business rules.

All reads return plain dictionaries. All writes run inside an
:class:`InventoryStore` transaction, so the dataset is validated and persisted
atomically. Sensitive methods accept an optional ``operation_id``; when it is
present, the mutation and its idempotency record are stored in the same
transaction, which makes an interrupted approval safe to resume.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from agentic_chatbot.inventory.data_access import InventoryStore

DHAKA = ZoneInfo("Asia/Dhaka")
CURRENCY = "BDT"
TAX_PERCENT = 5

OPEN_INVOICE_STATUSES = {"unpaid", "partially_paid", "overdue"}
PAYMENT_METHODS = {"cash", "bank_transfer", "mobile_banking", "card"}

PURCHASE_ORDER_TRANSITIONS = {
    "draft": {"pending_approval", "cancelled"},
    "pending_approval": {"approved", "rejected", "cancelled"},
    "approved": {"ordered", "cancelled"},
    "ordered": {"partially_received", "received", "cancelled"},
    "partially_received": {"received", "cancelled"},
    "received": set(),
    "rejected": set(),
    "cancelled": set(),
}


class InventoryError(ValueError):
    """A business-rule violation that should be shown to the model."""


def _now_date() -> str:
    return datetime.now(DHAKA).date().isoformat()


def _now_timestamp() -> str:
    return datetime.now(DHAKA).isoformat(timespec="seconds")


def _tax(taxable: int) -> int:
    return (taxable * TAX_PERCENT + 50) // 100


def _number(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InventoryError(f"{field_name} must be a number.")
    if float(value) != int(value):
        raise InventoryError(f"{field_name} must be a whole number.")
    return int(value)


def _positive(value: Any, field_name: str) -> int:
    result = _number(value, field_name)
    if result <= 0:
        raise InventoryError(f"{field_name} must be greater than zero.")
    return result


def _non_negative(value: Any, field_name: str) -> int:
    result = _number(value, field_name)
    if result < 0:
        raise InventoryError(f"{field_name} must not be negative.")
    return result


def _text(value: Any, field_name: str, *, optional: bool = False) -> str:
    if value is None and optional:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise InventoryError(f"{field_name} is required.")
    return value.strip()


def _find(rows: list[dict], field_name: str, value: Any) -> dict | None:
    for row in rows:
        if row.get(field_name) == value:
            return row
    return None


def _require(rows: list[dict], field_name: str, value: Any, label: str) -> dict:
    row = _find(rows, field_name, value)
    if row is None:
        raise InventoryError(f"{label} not found: {value}.")
    return row


def _search_terms(query: str) -> list[str]:
    """Tokenise a query and fold simple plurals so "laptops" finds "laptop"."""
    terms = []
    for raw in re.split(r"[^a-z0-9]+", query.lower()):
        if not raw:
            continue
        terms.append(raw[:-1] if len(raw) > 3 and raw.endswith("s") else raw)
    return terms


def _search_matches(haystack: str, query: str) -> bool:
    needle = query.strip().lower()
    if not needle:
        return True
    if needle in haystack:
        return True
    terms = _search_terms(needle)
    return bool(terms) and all(term in haystack for term in terms)


def _cached_operation(data: dict, operation_id: str | None) -> dict | None:
    if not operation_id:
        return None
    for row in data.get("operation_log", []):
        if row.get("operation_id") == operation_id:
            result = row.get("result")
            return result if isinstance(result, dict) else {"result": result}
    return None


def _append_operation_log(
    data: dict,
    operation_id: str | None,
    tool: str,
    result: dict,
    limit: int | None = None,
) -> None:
    if not operation_id:
        return
    rows = data.setdefault("operation_log", [])
    rows.append(
        {
            "operation_id": operation_id,
            "tool": tool,
            "executed_at": _now_timestamp(),
            "result": result,
        }
    )
    if limit and len(rows) > limit:
        data["operation_log"] = rows[-limit:]


class InventoryService:
    def __init__(
        self,
        store: InventoryStore,
        *,
        operation_log_limit: int = 500,
        audit_log_limit: int = 1000,
    ):
        self.store = store
        self.operation_log_limit = max(1, int(operation_log_limit))
        self.audit_log_limit = max(1, int(audit_log_limit))

    def _record_operation(
        self, data: dict, operation_id: str | None, tool: str, result: dict
    ) -> None:
        _append_operation_log(
            data,
            operation_id,
            tool,
            result,
            limit=self.operation_log_limit,
        )

    # =====================================================================
    # products and categories
    # =====================================================================

    def list_products(
        self, category_id: str = "", active_only: bool = True, limit: int = 50
    ) -> dict:
        data = self.store.snapshot()
        rows = [row for row in data["products"] if not active_only or row["is_active"]]
        if category_id:
            category = _require(data["categories"], "category_id", category_id, "Category")
            ids = self._category_scope(data["categories"], category["category_id"])
            rows = [row for row in rows if row["category_id"] in ids]
        return {
            "count": len(rows),
            "products": [
                self._decorate_product(data, row)
                for row in rows[: max(1, min(int(limit), 200))]
            ],
        }

    def get_product(self, product_id: str) -> dict:
        data = self.store.snapshot()
        product = self._lookup_product(data, product_id)
        return {
            "product": self._decorate_product(data, product),
            "stock": self._product_stock(data, product["product_id"]),
        }

    def search_products(
        self, query: str, category_id: str = "", active_only: bool = True
    ) -> dict:
        query = _text(query, "query")
        data = self.store.snapshot()
        rows = []
        for row in data["products"]:
            if active_only and not row["is_active"]:
                continue
            if category_id and row["category_id"] != category_id:
                continue
            haystack = " ".join(
                str(row.get(field, ""))
                for field in ("product_id", "sku", "name", "description", "barcode")
            ).lower()
            if _search_matches(haystack, query):
                rows.append(row)
        return {
            "query": query,
            "count": len(rows),
            "products": [self._decorate_product(data, row) for row in rows],
        }

    def create_product(
        self,
        sku: str,
        name: str,
        category_id: str,
        unit_id: str,
        supplier_id: str,
        purchase_price: Any,
        selling_price: Any,
        description: str,
        reorder_level: Any = 0,
        barcode: str = "",
        operation_id: str | None = None,
    ) -> dict:
        sku = _text(sku, "sku")
        name = _text(name, "name")
        description = _text(description, "description")
        purchase = _non_negative(purchase_price, "purchase_price")
        selling = _non_negative(selling_price, "selling_price")
        reorder = _non_negative(reorder_level, "reorder_level")
        if selling < purchase:
            raise InventoryError("selling_price must not be below purchase_price.")
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            if any(row["sku"].lower() == sku.lower() for row in data["products"]):
                raise InventoryError(f"A product with SKU {sku} already exists.")
            _require(data["categories"], "category_id", category_id, "Category")
            _require(data["units"], "unit_id", unit_id, "Unit")
            _require(data["suppliers"], "supplier_id", supplier_id, "Supplier")
            product_id = self.store.next_id(
                data, "products", "product_id", "PRD", width=4
            )
            now = _now_timestamp()
            product = {
                "product_id": product_id,
                "sku": sku,
                "name": name,
                "category_id": category_id,
                "unit_id": unit_id,
                "supplier_id": supplier_id,
                "description": description,
                "purchase_price": purchase,
                "selling_price": selling,
                "reorder_level": reorder,
                "barcode": barcode.strip() or f"8801{int(product_id.split('-')[1]):08d}",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            data["products"].append(product)
            result = {"product": self._decorate_product(data, product)}
            self._record_operation(data, operation_id, "create_product", result)
            return result

    def update_product(
        self,
        product_id: str,
        name: str | None = None,
        category_id: str | None = None,
        unit_id: str | None = None,
        supplier_id: str | None = None,
        description: str | None = None,
        purchase_price: Any = None,
        selling_price: Any = None,
        reorder_level: Any = None,
        is_active: bool | None = None,
        operation_id: str | None = None,
    ) -> dict:
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            product = self._lookup_product(data, product_id)
            before = dict(product)

            if name is not None:
                product["name"] = _text(name, "name")
            if description is not None:
                product["description"] = _text(description, "description")
            if category_id is not None:
                _require(data["categories"], "category_id", category_id, "Category")
                product["category_id"] = category_id
            if unit_id is not None:
                _require(data["units"], "unit_id", unit_id, "Unit")
                product["unit_id"] = unit_id
            if supplier_id is not None:
                _require(data["suppliers"], "supplier_id", supplier_id, "Supplier")
                product["supplier_id"] = supplier_id
            if purchase_price is not None:
                product["purchase_price"] = _non_negative(purchase_price, "purchase_price")
            if selling_price is not None:
                product["selling_price"] = _non_negative(selling_price, "selling_price")
            if reorder_level is not None:
                product["reorder_level"] = _non_negative(reorder_level, "reorder_level")
            if is_active is not None:
                product["is_active"] = bool(is_active)

            if product["selling_price"] < product["purchase_price"]:
                raise InventoryError("selling_price must not be below purchase_price.")

            product["updated_at"] = _now_timestamp()
            result = {
                "product": self._decorate_product(data, product),
                "previous": self._decorate_product(data, before),
            }
            self._record_operation(data, operation_id, "update_product", result)
            return result

    def deactivate_product(
        self, product_id: str, reason: str = "", operation_id: str | None = None
    ) -> dict:
        """Soft-delete a product. Historical transactions keep referencing it."""
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            product = self._lookup_product(data, product_id)
            if not product["is_active"]:
                result = {
                    "product": self._decorate_product(data, product),
                    "message": "Product was already inactive.",
                }
            else:
                product["is_active"] = False
                product["updated_at"] = _now_timestamp()
                result = {
                    "product": self._decorate_product(data, product),
                    "message": (
                        "Product deactivated (soft delete). Historical sales, "
                        "purchase orders, and stock movements were preserved."
                    ),
                    "reason": reason.strip(),
                }
            self._record_operation(data, operation_id, "deactivate_product", result)
            return result

    def list_categories(self, active_only: bool = True) -> dict:
        data = self.store.snapshot()
        categories = [
            row for row in data["categories"] if not active_only or row["is_active"]
        ]
        counts: dict[str, int] = {}
        for product in data["products"]:
            counts[product["category_id"]] = counts.get(product["category_id"], 0) + 1
        return {
            "count": len(categories),
            "categories": [
                {**row, "product_count": counts.get(row["category_id"], 0)}
                for row in categories
            ],
        }

    def create_category(
        self,
        name: str,
        description: str,
        parent_category_id: str = "",
        operation_id: str | None = None,
    ) -> dict:
        name = _text(name, "name")
        description = _text(description, "description")
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            if any(row["name"].lower() == name.lower() for row in data["categories"]):
                raise InventoryError(f"A category named {name} already exists.")
            if parent_category_id:
                _require(
                    data["categories"], "category_id", parent_category_id, "Parent category"
                )
            category_id = self.store.next_id(
                data, "categories", "category_id", "CAT", width=3
            )
            category = {
                "category_id": category_id,
                "name": name,
                "description": description,
                "parent_category_id": parent_category_id or None,
                "is_active": True,
            }
            data["categories"].append(category)
            result = {"category": category}
            self._record_operation(data, operation_id, "create_category", result)
            return result

    def update_category(
        self,
        category_id: str,
        name: str | None = None,
        description: str | None = None,
        parent_category_id: str | None = None,
        is_active: bool | None = None,
        operation_id: str | None = None,
    ) -> dict:
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            category = _require(
                data["categories"], "category_id", category_id, "Category"
            )
            if name is not None:
                category["name"] = _text(name, "name")
            if description is not None:
                category["description"] = _text(description, "description")
            if parent_category_id is not None:
                if parent_category_id:
                    _require(
                        data["categories"], "category_id", parent_category_id, "Parent category"
                    )
                    if parent_category_id == category_id:
                        raise InventoryError("A category cannot be its own parent.")
                category["parent_category_id"] = parent_category_id or None
            if is_active is not None:
                category["is_active"] = bool(is_active)
            result = {"category": category}
            self._record_operation(data, operation_id, "update_category", result)
            return result

    # =====================================================================
    # stock
    # =====================================================================

    def get_stock(self, product_id: str = "", warehouse_id: str = "") -> dict:
        data = self.store.snapshot()
        rows = data["stock"]
        if product_id:
            product = self._lookup_product(data, product_id)
            rows = [row for row in rows if row["product_id"] == product["product_id"]]
        if warehouse_id:
            _require(data["warehouses"], "warehouse_id", warehouse_id, "Warehouse")
            rows = [row for row in rows if row["warehouse_id"] == warehouse_id]
        return {
            "count": len(rows),
            "stock": [self._decorate_stock(data, row) for row in rows],
        }

    def check_low_stock(self, warehouse_id: str = "") -> dict:
        data = self.store.snapshot()
        if warehouse_id:
            _require(data["warehouses"], "warehouse_id", warehouse_id, "Warehouse")
        rows = []
        for product in data["products"]:
            if not product["is_active"]:
                continue
            available = self._available(
                data, product["product_id"], warehouse_id or None
            )
            if available <= product["reorder_level"]:
                rows.append(
                    {
                        "product_id": product["product_id"],
                        "sku": product["sku"],
                        "name": product["name"],
                        "warehouse_id": warehouse_id or "ALL",
                        "available_quantity": available,
                        "reorder_level": product["reorder_level"],
                        "shortfall": max(product["reorder_level"] - available, 0),
                        "out_of_stock": available <= 0,
                    }
                )
        rows.sort(key=lambda row: (row["available_quantity"], row["product_id"]))
        return {"count": len(rows), "low_stock": rows}

    def check_product_availability(
        self, product_id: str, warehouse_id: str = ""
    ) -> dict:
        data = self.store.snapshot()
        product = self._lookup_product(data, product_id)
        if warehouse_id:
            _require(data["warehouses"], "warehouse_id", warehouse_id, "Warehouse")
        rows = [
            self._decorate_stock(data, row)
            for row in data["stock"]
            if row["product_id"] == product["product_id"]
            and (not warehouse_id or row["warehouse_id"] == warehouse_id)
        ]
        total = sum(row["available_quantity"] for row in rows)
        return {
            "product_id": product["product_id"],
            "sku": product["sku"],
            "name": product["name"],
            "warehouse_id": warehouse_id or "ALL",
            "available_quantity": total,
            "is_available": total > 0,
            "locations": rows,
        }

    def adjust_stock(
        self,
        product_id: str,
        warehouse_id: str,
        quantity_change: Any,
        reason: str,
        performed_by: str,
        operation_id: str | None = None,
    ) -> dict:
        change = _number(quantity_change, "quantity_change")
        if change == 0:
            raise InventoryError("quantity_change must not be zero.")
        reason = _text(reason, "reason")
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            product = self._lookup_product(data, product_id)
            _require(data["warehouses"], "warehouse_id", warehouse_id, "Warehouse")
            _require(data["employees"], "employee_id", performed_by, "Employee")
            stock = self._stock_row(data, product["product_id"], warehouse_id)
            if stock is None:
                if change < 0:
                    raise InventoryError(
                        f"No stock record for {product['product_id']} at {warehouse_id}."
                    )
                stock = self._create_stock_row(data, product["product_id"], warehouse_id)
            before = stock["quantity_on_hand"]
            new_on_hand = before + change
            if new_on_hand < 0:
                raise InventoryError("Adjustment would make quantity_on_hand negative.")
            if new_on_hand < stock["quantity_reserved"]:
                raise InventoryError(
                    "Adjustment would make available quantity negative "
                    f"({new_on_hand} on hand, {stock['quantity_reserved']} reserved)."
                )
            stock["quantity_on_hand"] = new_on_hand
            stock["updated_at"] = _now_timestamp()
            movement = self._add_movement(
                data,
                product["product_id"],
                warehouse_id,
                "stock_adjustment",
                change,
                f"ADJ-{date.today().isoformat()}-{len(data['stock_movements']) + 1:04d}",
                _now_date(),
                performed_by,
                reason,
            )
            result = {
                "product_id": product["product_id"],
                "warehouse_id": warehouse_id,
                "previous_on_hand": before,
                "new_on_hand": new_on_hand,
                "quantity_reserved": stock["quantity_reserved"],
                "available_quantity": new_on_hand - stock["quantity_reserved"],
                "movement": movement,
                "reason": reason,
            }
            self._record_operation(data, operation_id, "adjust_stock", result)
            return result

    def transfer_stock(
        self,
        product_id: str,
        from_warehouse_id: str,
        to_warehouse_id: str,
        quantity: Any,
        performed_by: str,
        reason: str = "",
        operation_id: str | None = None,
    ) -> dict:
        quantity = _positive(quantity, "quantity")
        if from_warehouse_id == to_warehouse_id:
            raise InventoryError("Source and destination warehouses must differ.")
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            product = self._lookup_product(data, product_id)
            _require(data["warehouses"], "warehouse_id", from_warehouse_id, "Source warehouse")
            _require(data["warehouses"], "warehouse_id", to_warehouse_id, "Destination warehouse")
            _require(data["employees"], "employee_id", performed_by, "Employee")
            source = self._stock_row(data, product["product_id"], from_warehouse_id)
            if source is None:
                raise InventoryError("The product has no stock at the source warehouse.")
            available = source["quantity_on_hand"] - source["quantity_reserved"]
            if available < quantity:
                raise InventoryError(
                    f"Insufficient available stock: {available} available, {quantity} requested."
                )
            source["quantity_on_hand"] -= quantity
            source["updated_at"] = _now_timestamp()
            destination = self._stock_row(data, product["product_id"], to_warehouse_id)
            if destination is None:
                destination = self._create_stock_row(
                    data, product["product_id"], to_warehouse_id
                )
            destination["quantity_on_hand"] += quantity
            destination["updated_at"] = _now_timestamp()
            reference = f"TRN-{date.today().isoformat()}-{len(data['stock_movements']) + 1:04d}"
            note = reason.strip() or "Inter-warehouse stock transfer."
            out_movement = self._add_movement(
                data, product["product_id"], from_warehouse_id, "transfer_out",
                -quantity, reference, _now_date(), performed_by, note,
            )
            in_movement = self._add_movement(
                data, product["product_id"], to_warehouse_id, "transfer_in",
                quantity, reference, _now_date(), performed_by, note,
            )
            result = {
                "product_id": product["product_id"],
                "from_warehouse_id": from_warehouse_id,
                "to_warehouse_id": to_warehouse_id,
                "quantity": quantity,
                "reference": reference,
                "movements": [out_movement, in_movement],
            }
            self._record_operation(data, operation_id, "transfer_stock", result)
            return result

    def get_stock_movements(
        self,
        product_id: str = "",
        warehouse_id: str = "",
        movement_type: str = "",
        limit: int = 50,
    ) -> dict:
        data = self.store.snapshot()
        rows = data["stock_movements"]
        if product_id:
            product = self._lookup_product(data, product_id)
            rows = [row for row in rows if row["product_id"] == product["product_id"]]
        if warehouse_id:
            rows = [row for row in rows if row["warehouse_id"] == warehouse_id]
        if movement_type:
            rows = [row for row in rows if row["movement_type"] == movement_type]
        rows = sorted(rows, key=lambda row: (row["movement_date"], row["movement_id"]), reverse=True)
        return {
            "count": len(rows),
            "movements": rows[: max(1, min(int(limit), 200))],
        }

    # =====================================================================
    # customers and suppliers
    # =====================================================================

    def list_customers(self, active_only: bool = True, limit: int = 50) -> dict:
        data = self.store.snapshot()
        rows = [row for row in data["customers"] if not active_only or row["is_active"]]
        return {
            "count": len(rows),
            "customers": rows[: max(1, min(int(limit), 200))],
        }

    def get_customer(self, customer_id: str) -> dict:
        data = self.store.snapshot()
        customer = _require(data["customers"], "customer_id", customer_id, "Customer")
        invoices = [
            row for row in data["invoices"] if row["customer_id"] == customer_id
        ]
        sales = [row for row in data["sales"] if row["customer_id"] == customer_id]
        return {
            "customer": customer,
            "open_invoices": [self._decorate_invoice(data, row) for row in invoices if row["status"] in OPEN_INVOICE_STATUSES],
            "invoice_count": len(invoices),
            "sale_count": len(sales),
            "outstanding_balance": customer["outstanding_balance"],
        }

    def search_customers(self, query: str, active_only: bool = True) -> dict:
        query = _text(query, "query")
        data = self.store.snapshot()
        rows = [
            row
            for row in data["customers"]
            if (not active_only or row["is_active"])
            and _search_matches(
                " ".join(
                    str(row.get(field, ""))
                    for field in (
                        "customer_id",
                        "name",
                        "email",
                        "phone",
                        "contact_person",
                    )
                ).lower(),
                query,
            )
        ]
        return {"query": query, "count": len(rows), "customers": rows}

    def create_customer(
        self,
        name: str,
        customer_type: str,
        email: str,
        phone: str,
        billing_address: str,
        shipping_address: str,
        contact_person: str = "",
        credit_limit: Any = 0,
        operation_id: str | None = None,
    ) -> dict:
        name = _text(name, "name")
        if customer_type not in {"individual", "business"}:
            raise InventoryError("customer_type must be 'individual' or 'business'.")
        limit = _non_negative(credit_limit, "credit_limit")
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            customer_id = self.store.next_id(
                data, "customers", "customer_id", "CUS", width=3
            )
            customer = {
                "customer_id": customer_id,
                "name": name,
                "customer_type": customer_type,
                "contact_person": contact_person.strip(),
                "email": _text(email, "email"),
                "phone": _text(phone, "phone"),
                "billing_address": _text(billing_address, "billing_address"),
                "shipping_address": _text(shipping_address, "shipping_address"),
                "credit_limit": limit,
                "outstanding_balance": 0,
                "is_active": True,
                "created_at": _now_timestamp(),
            }
            data["customers"].append(customer)
            result = {"customer": customer}
            self._record_operation(data, operation_id, "create_customer", result)
            return result

    def update_customer(
        self,
        customer_id: str,
        name: str | None = None,
        contact_person: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        billing_address: str | None = None,
        shipping_address: str | None = None,
        credit_limit: Any = None,
        is_active: bool | None = None,
        operation_id: str | None = None,
    ) -> dict:
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            customer = _require(data["customers"], "customer_id", customer_id, "Customer")
            before = dict(customer)
            if name is not None:
                customer["name"] = _text(name, "name")
            if contact_person is not None:
                customer["contact_person"] = contact_person.strip()
            if email is not None:
                customer["email"] = _text(email, "email")
            if phone is not None:
                customer["phone"] = _text(phone, "phone")
            if billing_address is not None:
                customer["billing_address"] = _text(billing_address, "billing_address")
            if shipping_address is not None:
                customer["shipping_address"] = _text(shipping_address, "shipping_address")
            if credit_limit is not None:
                limit = _non_negative(credit_limit, "credit_limit")
                if customer["outstanding_balance"] > limit:
                    raise InventoryError(
                        "The new credit_limit is below the customer's outstanding balance."
                    )
                customer["credit_limit"] = limit
            if is_active is not None:
                customer["is_active"] = bool(is_active)
            result = {"customer": customer, "previous": before}
            self._record_operation(data, operation_id, "update_customer", result)
            return result

    def list_suppliers(self, active_only: bool = True, limit: int = 50) -> dict:
        data = self.store.snapshot()
        rows = [row for row in data["suppliers"] if not active_only or row["is_active"]]
        return {"count": len(rows), "suppliers": rows[: max(1, min(int(limit), 200))]}

    def get_supplier(self, supplier_id: str) -> dict:
        data = self.store.snapshot()
        supplier = _require(data["suppliers"], "supplier_id", supplier_id, "Supplier")
        products = [
            {"product_id": row["product_id"], "sku": row["sku"], "name": row["name"]}
            for row in data["products"]
            if row["supplier_id"] == supplier_id
        ]
        orders = [
            row for row in data["purchase_orders"] if row["supplier_id"] == supplier_id
        ]
        return {
            "supplier": supplier,
            "product_count": len(products),
            "products": products,
            "purchase_order_count": len(orders),
        }

    def search_suppliers(self, query: str, active_only: bool = True) -> dict:
        query = _text(query, "query")
        data = self.store.snapshot()
        rows = [
            row
            for row in data["suppliers"]
            if (not active_only or row["is_active"])
            and _search_matches(
                " ".join(
                    str(row.get(field, ""))
                    for field in (
                        "supplier_id",
                        "name",
                        "email",
                        "phone",
                        "contact_person",
                    )
                ).lower(),
                query,
            )
        ]
        return {"query": query, "count": len(rows), "suppliers": rows}

    # =====================================================================
    # sales and invoices
    # =====================================================================

    def list_sales(
        self,
        customer_id: str = "",
        employee_id: str = "",
        status: str = "",
        limit: int = 50,
    ) -> dict:
        data = self.store.snapshot()
        rows = data["sales"]
        if customer_id:
            rows = [row for row in rows if row["customer_id"] == customer_id]
        if employee_id:
            rows = [row for row in rows if row["sales_employee_id"] == employee_id]
        if status:
            rows = [row for row in rows if row["status"] == status]
        rows = sorted(rows, key=lambda row: (row["sale_date"], row["sale_id"]), reverse=True)
        return {
            "count": len(rows),
            "sales": [self._decorate_sale(data, row) for row in rows[: max(1, min(int(limit), 200))]],
        }

    def get_sale(self, sale_id: str) -> dict:
        data = self.store.snapshot()
        sale = _require(data["sales"], "sale_id", sale_id, "Sale")
        items = [
            {
                **item,
                "product_name": self._lookup_product(data, item["product_id"])["name"],
            }
            for item in data["sale_items"]
            if item["sale_id"] == sale_id
        ]
        invoice = _find(data["invoices"], "sale_id", sale_id)
        return {
            "sale": self._decorate_sale(data, sale),
            "items": items,
            "invoice": self._decorate_invoice(data, invoice) if invoice else None,
        }

    def create_sale(
        self,
        customer_id: str,
        sales_employee_id: str,
        warehouse_id: str,
        items: list[dict],
        discount: Any = 0,
        status: str = "pending_approval",
        operation_id: str | None = None,
    ) -> dict:
        if status not in {"draft", "pending_approval"}:
            raise InventoryError("New sales must be created as draft or pending_approval.")
        discount = _non_negative(discount, "discount")
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            lines = self._normalise_items(
                data, items, price_field="unit_price", use_selling=True
            )
            _require(data["customers"], "customer_id", customer_id, "Customer")
            _require(data["employees"], "employee_id", sales_employee_id, "Employee")
            _require(data["warehouses"], "warehouse_id", warehouse_id, "Warehouse")
            subtotal = sum(line["line_total"] for line in lines)
            if discount > subtotal:
                raise InventoryError("discount must not exceed the sale subtotal.")
            sale_id = self.store.next_id(data, "sales", "sale_id", "SALE-2026", width=3)
            sale = {
                "sale_id": sale_id,
                "sale_date": _now_date(),
                "customer_id": customer_id,
                "sales_employee_id": sales_employee_id,
                "warehouse_id": warehouse_id,
                "status": status,
                "subtotal": subtotal,
                "discount": discount,
                "tax": _tax(subtotal - discount),
                "total": subtotal - discount + _tax(subtotal - discount),
                "currency": CURRENCY,
            }
            data["sales"].append(sale)
            for index, line in enumerate(lines, start=1):
                data["sale_items"].append(
                    {
                        "sale_item_id": f"{sale_id}-{index:02d}",
                        "sale_id": sale_id,
                        "product_id": line["product_id"],
                        "quantity": line["quantity"],
                        "unit_price": line["unit_price"],
                        "line_total": line["line_total"],
                    }
                )
            result = {"sale": self._decorate_sale(data, sale), "items": lines}
            self._record_operation(data, operation_id, "create_sale", result)
            return result

    def update_sale(
        self,
        sale_id: str,
        status: str | None = None,
        discount: Any = None,
        operation_id: str | None = None,
    ) -> dict:
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            sale = _require(data["sales"], "sale_id", sale_id, "Sale")
            items = [row for row in data["sale_items"] if row["sale_id"] == sale_id]
            before = dict(sale)

            if discount is not None:
                if sale["status"] not in {"draft", "pending_approval"}:
                    raise InventoryError("Discount can only change before confirmation.")
                value = _non_negative(discount, "discount")
                if value > sale["subtotal"]:
                    raise InventoryError("discount must not exceed the sale subtotal.")
                sale["discount"] = value
                sale["tax"] = _tax(sale["subtotal"] - value)
                sale["total"] = sale["subtotal"] - value + sale["tax"]

            if status is not None:
                if status == sale["status"]:
                    pass
                elif status == "confirmed":
                    if sale["status"] != "pending_approval":
                        raise InventoryError("Only a pending_approval sale can be confirmed.")
                    self._reserve_and_deduct_sale_stock(data, sale, items)
                    sale["status"] = "confirmed"
                elif status == "cancelled":
                    self._cancel_sale_locked(data, sale, items, "Sale cancelled.")
                elif status == "invoiced":
                    raise InventoryError("Use create_invoice to invoice a sale.")
                else:
                    raise InventoryError(f"Unsupported sale transition to {status!r}.")

            result = {
                "sale": self._decorate_sale(data, sale),
                "previous": self._decorate_sale(data, before),
            }
            self._record_operation(data, operation_id, "update_sale", result)
            return result

    def cancel_sale(
        self, sale_id: str, reason: str = "", operation_id: str | None = None
    ) -> dict:
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            sale = _require(data["sales"], "sale_id", sale_id, "Sale")
            items = [row for row in data["sale_items"] if row["sale_id"] == sale_id]
            self._cancel_sale_locked(data, sale, items, reason or "Sale cancelled.")
            result = {"sale": self._decorate_sale(data, sale)}
            self._record_operation(data, operation_id, "cancel_sale", result)
            return result

    def get_sales_by_customer(self, customer_id: str) -> dict:
        _require(self.store.snapshot()["customers"], "customer_id", customer_id, "Customer")
        return self.list_sales(customer_id=customer_id, limit=200)

    def get_sales_by_employee(self, employee_id: str) -> dict:
        _require(self.store.snapshot()["employees"], "employee_id", employee_id, "Employee")
        return self.list_sales(employee_id=employee_id, limit=200)

    def list_invoices(
        self, customer_id: str = "", status: str = "", limit: int = 50
    ) -> dict:
        data = self.store.snapshot()
        rows = data["invoices"]
        if customer_id:
            rows = [row for row in rows if row["customer_id"] == customer_id]
        if status:
            rows = [row for row in rows if row["status"] == status]
        rows = sorted(rows, key=lambda row: (row["issue_date"], row["invoice_id"]), reverse=True)
        return {
            "count": len(rows),
            "invoices": [
                self._decorate_invoice(data, row)
                for row in rows[: max(1, min(int(limit), 200))]
            ],
        }

    def get_invoice(self, invoice_id: str) -> dict:
        data = self.store.snapshot()
        invoice = _require(data["invoices"], "invoice_id", invoice_id, "Invoice")
        payments = [
            row for row in data["payments"] if row["invoice_id"] == invoice_id
        ]
        return {
            "invoice": self._decorate_invoice(data, invoice),
            "payments": payments,
        }

    def create_invoice(
        self, sale_id: str, due_days: Any = 30, operation_id: str | None = None
    ) -> dict:
        days = _non_negative(due_days, "due_days")
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            sale = _require(data["sales"], "sale_id", sale_id, "Sale")
            if sale["status"] != "confirmed":
                raise InventoryError("Only a confirmed sale can be invoiced.")
            if _find(data["invoices"], "sale_id", sale_id) is not None:
                raise InventoryError("This sale already has an invoice.")
            invoice_id = self.store.next_id(
                data, "invoices", "invoice_id", "INV-2026", width=3
            )
            issue = date.today()
            invoice = {
                "invoice_id": invoice_id,
                "sale_id": sale_id,
                "customer_id": sale["customer_id"],
                "issue_date": issue.isoformat(),
                "due_date": (issue + timedelta(days=days)).isoformat(),
                "status": "unpaid",
                "total": sale["total"],
                "amount_paid": 0,
                "balance_due": sale["total"],
            }
            data["invoices"].append(invoice)
            sale["status"] = "invoiced"
            self._recompute_customer_balance(data, sale["customer_id"])
            result = {"invoice": self._decorate_invoice(data, invoice)}
            self._record_operation(data, operation_id, "create_invoice", result)
            return result

    def record_payment(
        self,
        invoice_id: str,
        amount: Any,
        method: str,
        reference: str = "",
        payment_date: str = "",
        operation_id: str | None = None,
    ) -> dict:
        amount = _positive(amount, "amount")
        if method not in PAYMENT_METHODS:
            raise InventoryError(f"method must be one of {sorted(PAYMENT_METHODS)}.")
        when = payment_date or _now_date()
        date.fromisoformat(when)
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            invoice = _require(data["invoices"], "invoice_id", invoice_id, "Invoice")
            if invoice["status"] in {"paid", "cancelled", "draft"}:
                raise InventoryError(f"Invoice {invoice_id} is not open for payment.")
            if amount > invoice["balance_due"]:
                raise InventoryError(
                    f"Payment {amount} exceeds the outstanding balance "
                    f"{invoice['balance_due']} on {invoice_id}."
                )
            payment_id = self.store.next_id(
                data, "payments", "payment_id", "PAY-2026", width=3
            )
            payment = {
                "payment_id": payment_id,
                "invoice_id": invoice_id,
                "customer_id": invoice["customer_id"],
                "payment_date": when,
                "amount": amount,
                "method": method,
                "reference": reference.strip() or f"RCPT-{payment_id}",
                "status": "completed",
            }
            data["payments"].append(payment)
            invoice["amount_paid"] += amount
            invoice["balance_due"] = invoice["total"] - invoice["amount_paid"]
            invoice["status"] = "paid" if invoice["balance_due"] == 0 else "partially_paid"
            sale = _find(data["sales"], "sale_id", invoice["sale_id"])
            if sale is not None:
                sale["status"] = "paid" if invoice["balance_due"] == 0 else "partially_paid"
            self._recompute_customer_balance(data, invoice["customer_id"])
            result = {
                "payment": payment,
                "invoice": self._decorate_invoice(data, invoice),
                "customer_outstanding_balance": self._customer_balance(
                    data, invoice["customer_id"]
                ),
            }
            self._record_operation(data, operation_id, "record_payment", result)
            return result

    def get_outstanding_invoices(self, customer_id: str = "") -> dict:
        data = self.store.snapshot()
        rows = [
            row
            for row in data["invoices"]
            if row["status"] in OPEN_INVOICE_STATUSES and row["balance_due"] > 0
        ]
        if customer_id:
            _require(data["customers"], "customer_id", customer_id, "Customer")
            rows = [row for row in rows if row["customer_id"] == customer_id]
        rows = sorted(rows, key=lambda row: row["due_date"])
        return {
            "count": len(rows),
            "total_outstanding": sum(row["balance_due"] for row in rows),
            "invoices": [self._decorate_invoice(data, row) for row in rows],
        }

    def get_customer_balance(self, customer_id: str) -> dict:
        data = self.store.snapshot()
        customer = _require(data["customers"], "customer_id", customer_id, "Customer")
        invoices = [
            self._decorate_invoice(data, row)
            for row in data["invoices"]
            if row["customer_id"] == customer_id
        ]
        open_invoices = [
            row for row in invoices if row["status"] in OPEN_INVOICE_STATUSES
        ]
        return {
            "customer_id": customer_id,
            "name": customer["name"],
            "currency": CURRENCY,
            "credit_limit": customer["credit_limit"],
            "outstanding_balance": customer["outstanding_balance"],
            "available_credit": customer["credit_limit"] - customer["outstanding_balance"],
            "open_invoice_count": len(open_invoices),
            "open_invoices": open_invoices,
            "all_invoices": invoices,
        }

    # =====================================================================
    # purchase orders
    # =====================================================================

    def list_purchase_orders(
        self, supplier_id: str = "", status: str = "", limit: int = 50
    ) -> dict:
        data = self.store.snapshot()
        rows = data["purchase_orders"]
        if supplier_id:
            rows = [row for row in rows if row["supplier_id"] == supplier_id]
        if status:
            rows = [row for row in rows if row["status"] == status]
        rows = sorted(rows, key=lambda row: (row["order_date"], row["purchase_order_id"]), reverse=True)
        return {
            "count": len(rows),
            "purchase_orders": [
                self._decorate_purchase_order(data, row)
                for row in rows[: max(1, min(int(limit), 200))]
            ],
        }

    def get_purchase_order(self, purchase_order_id: str) -> dict:
        data = self.store.snapshot()
        order = _require(
            data["purchase_orders"],
            "purchase_order_id",
            purchase_order_id,
            "Purchase order",
        )
        items = [
            {
                **item,
                "product_name": self._lookup_product(data, item["product_id"])["name"],
            }
            for item in data["purchase_order_items"]
            if item["purchase_order_id"] == purchase_order_id
        ]
        receipt = [
            row
            for row in data["stock_movements"]
            if row["movement_type"] == "purchase_receipt"
            and row["reference"] == purchase_order_id
        ]
        return {
            "purchase_order": self._decorate_purchase_order(data, order),
            "items": items,
            "receipts": receipt,
        }

    def create_purchase_order(
        self,
        supplier_id: str,
        warehouse_id: str,
        items: list[dict],
        created_by: str,
        expected_date: str = "",
        status: str = "pending_approval",
        operation_id: str | None = None,
    ) -> dict:
        if status not in {"draft", "pending_approval"}:
            raise InventoryError("New purchase orders must be draft or pending_approval.")
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            lines = self._normalise_items(
                data, items, price_field="unit_cost", use_selling=False
            )
            _require(data["suppliers"], "supplier_id", supplier_id, "Supplier")
            _require(data["warehouses"], "warehouse_id", warehouse_id, "Warehouse")
            _require(data["employees"], "employee_id", created_by, "Employee")
            if expected_date:
                date.fromisoformat(expected_date)
            po_id = self.store.next_id(
                data, "purchase_orders", "purchase_order_id", "PO-2026", width=3
            )
            order = {
                "purchase_order_id": po_id,
                "supplier_id": supplier_id,
                "warehouse_id": warehouse_id,
                "order_date": _now_date(),
                "expected_date": expected_date or _now_date(),
                "status": status,
                "created_by": created_by,
                "total": sum(line["line_total"] for line in lines),
                "currency": CURRENCY,
            }
            data["purchase_orders"].append(order)
            for index, line in enumerate(lines, start=1):
                data["purchase_order_items"].append(
                    {
                        "po_item_id": f"{po_id}-{index:02d}",
                        "purchase_order_id": po_id,
                        "product_id": line["product_id"],
                        "quantity": line["quantity"],
                        "unit_cost": line["unit_cost"],
                        "line_total": line["line_total"],
                    }
                )
            result = {
                "purchase_order": self._decorate_purchase_order(data, order),
                "items": lines,
            }
            self._record_operation(data, operation_id, "create_purchase_order", result)
            return result

    def update_purchase_order(
        self,
        purchase_order_id: str,
        status: str | None = None,
        expected_date: str | None = None,
        operation_id: str | None = None,
    ) -> dict:
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            order = _require(
                data["purchase_orders"],
                "purchase_order_id",
                purchase_order_id,
                "Purchase order",
            )
            before = dict(order)
            if expected_date is not None:
                date.fromisoformat(expected_date)
                order["expected_date"] = expected_date
            if status is not None and status != order["status"]:
                if status == "received":
                    raise InventoryError(
                        "Use receive_purchase_order to receive goods into stock."
                    )
                allowed = PURCHASE_ORDER_TRANSITIONS.get(order["status"], set())
                if status not in allowed:
                    raise InventoryError(
                        f"Cannot move purchase order from {order['status']!r} to {status!r}."
                    )
                order["status"] = status
            result = {
                "purchase_order": self._decorate_purchase_order(data, order),
                "previous": self._decorate_purchase_order(data, before),
            }
            self._record_operation(data, operation_id, "update_purchase_order", result)
            return result

    def receive_purchase_order(
        self, purchase_order_id: str, operation_id: str | None = None
    ) -> dict:
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            order = _require(
                data["purchase_orders"],
                "purchase_order_id",
                purchase_order_id,
                "Purchase order",
            )
            if order["status"] not in {"approved", "ordered", "partially_received"}:
                raise InventoryError(
                    "Only approved, ordered, or partially received purchase orders "
                    "can be received."
                )
            items = [
                row
                for row in data["purchase_order_items"]
                if row["purchase_order_id"] == purchase_order_id
            ]
            if not items:
                raise InventoryError("The purchase order has no items to receive.")
            received = []
            for item in items:
                stock = self._stock_row(
                    data, item["product_id"], order["warehouse_id"]
                )
                if stock is None:
                    stock = self._create_stock_row(
                        data, item["product_id"], order["warehouse_id"]
                    )
                stock["quantity_on_hand"] += item["quantity"]
                stock["updated_at"] = _now_timestamp()
                movement = self._add_movement(
                    data,
                    item["product_id"],
                    order["warehouse_id"],
                    "purchase_receipt",
                    item["quantity"],
                    purchase_order_id,
                    _now_date(),
                    order["created_by"],
                    "Goods received against the purchase order.",
                )
                received.append(movement)
            order["status"] = "received"
            result = {
                "purchase_order": self._decorate_purchase_order(data, order),
                "received_items": received,
            }
            self._record_operation(data, operation_id, "receive_purchase_order", result)
            return result

    # =====================================================================
    # finance
    # =====================================================================

    def list_accounts(self, account_type: str = "") -> dict:
        data = self.store.snapshot()
        rows = data["accounts"]
        if account_type:
            rows = [
                row
                for row in rows
                if row["account_type"].lower() == account_type.lower()
            ]
        return {"count": len(rows), "accounts": rows}

    def get_account(self, account: str) -> dict:
        data = self.store.snapshot()
        row = _find(data["accounts"], "account_id", account) or _find(
            data["accounts"], "account_code", account
        )
        if row is None:
            raise InventoryError(f"Account not found: {account}.")
        entries = [
            entry
            for entry in data["journal_entries"]
            if any(line["account_id"] == row["account_id"] for line in entry["lines"])
        ]
        return {"account": row, "journal_entries": entries}

    def list_expenses(
        self, status: str = "", limit: int = 50
    ) -> dict:
        data = self.store.snapshot()
        rows = data["expenses"]
        if status:
            rows = [row for row in rows if row["status"] == status]
        rows = sorted(rows, key=lambda row: (row["expense_date"], row["expense_id"]), reverse=True)
        return {
            "count": len(rows),
            "expenses": [
                self._decorate_expense(data, row)
                for row in rows[: max(1, min(int(limit), 200))]
            ],
        }

    def create_expense(
        self,
        account_id: str,
        description: str,
        amount: Any,
        payment_method: str,
        submitted_by: str,
        expense_date: str = "",
        status: str = "pending_approval",
        operation_id: str | None = None,
    ) -> dict:
        amount = _positive(amount, "amount")
        description = _text(description, "description")
        if payment_method not in PAYMENT_METHODS:
            raise InventoryError(f"payment_method must be one of {sorted(PAYMENT_METHODS)}.")
        if status not in {"draft", "pending_approval"}:
            raise InventoryError("New expenses must be draft or pending_approval.")
        when = expense_date or _now_date()
        date.fromisoformat(when)
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            account = _require(data["accounts"], "account_id", account_id, "Account")
            if account["account_type"] != "Expense":
                raise InventoryError("Expenses must be posted to an Expense account.")
            _require(data["employees"], "employee_id", submitted_by, "Employee")
            expense_id = self.store.next_id(
                data, "expenses", "expense_id", "EXP-2026", width=3
            )
            expense = {
                "expense_id": expense_id,
                "expense_date": when,
                "account_id": account_id,
                "description": description,
                "amount": amount,
                "payment_method": payment_method,
                "submitted_by": submitted_by,
                "status": status,
                "approved_by": "",
            }
            data["expenses"].append(expense)
            result = {"expense": self._decorate_expense(data, expense)}
            self._record_operation(data, operation_id, "create_expense", result)
            return result

    def get_financial_summary(self) -> dict:
        data = self.store.snapshot()
        receivable = sum(
            invoice["balance_due"]
            for invoice in data["invoices"]
            if invoice["status"] in OPEN_INVOICE_STATUSES
        )
        payable = sum(row["outstanding_balance"] for row in data["suppliers"])
        inventory_value = 0
        for row in data["stock"]:
            product = _find(data["products"], "product_id", row["product_id"])
            if product is not None:
                inventory_value += row["quantity_on_hand"] * product["purchase_price"]
        revenue = sum(
            sale["total"]
            for sale in data["sales"]
            if sale["status"] in {"invoiced", "partially_paid", "paid"}
        )
        expenses_total = sum(
            row["amount"]
            for row in data["expenses"]
            if row["status"] in {"approved", "paid"}
        )
        journal_balances: dict[str, int] = {}
        for entry in data["journal_entries"]:
            if entry["status"] != "posted":
                continue
            for line in entry["lines"]:
                journal_balances[line["account_id"]] = (
                    journal_balances.get(line["account_id"], 0)
                    + line["debit"]
                    - line["credit"]
                )
        return {
            "as_of": _now_date(),
            "currency": CURRENCY,
            "accounts_receivable": receivable,
            "accounts_payable": payable,
            "inventory_value_at_cost": inventory_value,
            "sales_revenue": revenue,
            "approved_expenses": expenses_total,
            "journal_net_debits": journal_balances,
            "note": (
                "Simplified demo summary. Journal balances are net debits and are "
                "not a full trial balance."
            ),
        }

    def get_sales_summary(self, period: str = "") -> dict:
        data = self.store.snapshot()
        rows = data["sales"]
        if period:
            rows = [row for row in rows if row["sale_date"].startswith(period)]
        by_status: dict[str, dict] = {}
        by_employee: dict[str, dict] = {}
        for sale in rows:
            status_bucket = by_status.setdefault(
                sale["status"], {"count": 0, "total": 0}
            )
            status_bucket["count"] += 1
            status_bucket["total"] += sale["total"]
            employee = _find(data["employees"], "employee_id", sale["sales_employee_id"])
            employee_name = employee["name"] if employee else sale["sales_employee_id"]
            employee_bucket = by_employee.setdefault(
                sale["sales_employee_id"],
                {"employee_id": sale["sales_employee_id"], "name": employee_name, "count": 0, "total": 0},
            )
            employee_bucket["count"] += 1
            employee_bucket["total"] += sale["total"]
        return {
            "period": period or "all",
            "currency": CURRENCY,
            "sale_count": len(rows),
            "total_sales_value": sum(row["total"] for row in rows),
            "by_status": by_status,
            "by_employee": list(by_employee.values()),
        }

    # =====================================================================
    # returns
    # =====================================================================

    def create_return_request(
        self,
        sale_id: str,
        product_id: str,
        quantity: Any,
        reason: str,
        refund_amount: Any = None,
        operation_id: str | None = None,
    ) -> dict:
        quantity = _positive(quantity, "quantity")
        reason = _text(reason, "reason")
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            sale = _require(data["sales"], "sale_id", sale_id, "Sale")
            if sale["status"] == "cancelled":
                raise InventoryError("A cancelled sale cannot have returns.")
            items = [
                row for row in data["sale_items"]
                if row["sale_id"] == sale_id and row["product_id"] == product_id
            ]
            if not items:
                raise InventoryError("The product does not appear on that sale.")
            sold = sum(row["quantity"] for row in items)
            already = sum(
                row["quantity"]
                for row in data["returns"]
                if row["sale_id"] == sale_id
                and row["product_id"] == product_id
                and row["status"] != "rejected"
            )
            if quantity > sold - already:
                raise InventoryError(
                    f"Only {sold - already} unit(s) of {product_id} remain returnable."
                )
            if refund_amount is None:
                refund = quantity * items[0]["unit_price"]
            else:
                refund = _non_negative(refund_amount, "refund_amount")
            return_id = self.store.next_id(
                data, "returns", "return_id", "RET-2026", width=3
            )
            record = {
                "return_id": return_id,
                "sale_id": sale_id,
                "customer_id": sale["customer_id"],
                "product_id": product_id,
                "quantity": quantity,
                "reason": reason,
                "requested_date": _now_date(),
                "status": "pending_review",
                "refund_amount": refund,
                "approved_by": "",
            }
            data["returns"].append(record)
            result = {"return": record}
            self._record_operation(data, operation_id, "create_return_request", result)
            return result

    def get_return(self, return_id: str) -> dict:
        data = self.store.snapshot()
        record = _require(data["returns"], "return_id", return_id, "Return")
        sale = _find(data["sales"], "sale_id", record["sale_id"])
        return {
            "return": record,
            "sale": self._decorate_sale(data, sale) if sale else None,
        }

    def list_returns(self, status: str = "", limit: int = 50) -> dict:
        data = self.store.snapshot()
        rows = data["returns"]
        if status:
            rows = [row for row in rows if row["status"] == status]
        rows = sorted(rows, key=lambda row: row["requested_date"], reverse=True)
        return {
            "count": len(rows),
            "returns": rows[: max(1, min(int(limit), 200))],
        }

    def process_return(
        self,
        return_id: str,
        decision: str = "approve",
        approver_id: str = "EMP-006",
        operation_id: str | None = None,
    ) -> dict:
        if decision not in {"approve", "reject"}:
            raise InventoryError("decision must be 'approve' or 'reject'.")
        with self.store.transaction() as data:
            cached = _cached_operation(data, operation_id)
            if cached is not None:
                return cached
            record = _require(data["returns"], "return_id", return_id, "Return")
            _require(data["employees"], "employee_id", approver_id, "Approver")
            sale = _require(data["sales"], "sale_id", record["sale_id"], "Sale")
            if record["status"] in {"processed", "rejected"}:
                return {"return": record, "message": "Return already finalised."}
            if decision == "reject":
                record["status"] = "rejected"
                record["approved_by"] = ""
                record["refund_amount"] = 0
                result = {"return": record, "message": "Return rejected."}
            else:
                stock = self._stock_row(
                    data, record["product_id"], sale["warehouse_id"]
                )
                if stock is None:
                    stock = self._create_stock_row(
                        data, record["product_id"], sale["warehouse_id"]
                    )
                stock["quantity_on_hand"] += record["quantity"]
                stock["updated_at"] = _now_timestamp()
                movement = self._add_movement(
                    data,
                    record["product_id"],
                    sale["warehouse_id"],
                    "sales_return",
                    record["quantity"],
                    return_id,
                    _now_date(),
                    approver_id,
                    f"Return processed: {record['reason']}",
                )
                record["status"] = "processed"
                record["approved_by"] = approver_id
                result = {
                    "return": record,
                    "movement": movement,
                    "refund_amount": record["refund_amount"],
                    "message": "Return approved, restocked, and refund recorded.",
                }
            self._record_operation(data, operation_id, "process_return", result)
            return result

    # =====================================================================
    # approvals and HITL support
    # =====================================================================

    def get_pending_approvals(self) -> dict:
        data = self.store.snapshot()
        rows = [row for row in data["approvals"] if row["status"] == "pending"]
        return {
            "count": len(rows),
            "approvals": [self._decorate_approval(data, row) for row in rows],
        }

    def get_approval_details(self, approval_id: str) -> dict:
        data = self.store.snapshot()
        row = _require(data["approvals"], "approval_id", approval_id, "Approval")
        return {"approval": self._decorate_approval(data, row)}

    def get_approval_history(
        self, resource_type: str = "", resource_id: str = ""
    ) -> dict:
        data = self.store.snapshot()
        rows = [row for row in data["approvals"] if row["status"] != "pending"]
        if resource_type:
            rows = [row for row in rows if row["resource_type"] == resource_type]
        if resource_id:
            rows = [row for row in rows if row["resource_id"] == resource_id]
        audit = [
            row
            for row in data["audit_log"]
            if row["action"].startswith("approval")
            and (not resource_type or row["resource_type"] == resource_type)
            and (not resource_id or row["resource_id"] == resource_id)
        ]
        return {"count": len(rows), "approvals": rows, "audit": audit}

    def preview_operation(self, tool_name: str, arguments: dict) -> dict:
        """Read-only preview used by the approval panel. Never mutates."""
        data = self.store.snapshot()
        summary: list[list[str]] = []
        warnings: list[str] = []

        def add(label: str, value: Any) -> None:
            summary.append([label, value])

        try:
            if tool_name in {"update_product", "deactivate_product"}:
                product = self._lookup_product(data, arguments.get("product_id", ""))
                add("Product", product["name"])
                add("SKU", product["sku"])
                if tool_name == "update_product":
                    if arguments.get("selling_price") is not None:
                        add("Current Selling Price", f"BDT {product['selling_price']:,}")
                        add("Proposed Selling Price", f"BDT {int(arguments['selling_price']):,}")
                    if arguments.get("purchase_price") is not None:
                        add("Current Purchase Price", f"BDT {product['purchase_price']:,}")
                        add("Proposed Purchase Price", f"BDT {int(arguments['purchase_price']):,}")
                    if arguments.get("reorder_level") is not None:
                        add("Current Reorder Level", product["reorder_level"])
                        add("Proposed Reorder Level", arguments["reorder_level"])
                    if arguments.get("name") is not None:
                        add("Proposed Name", arguments["name"])
                else:
                    add("Current Status", "active" if product["is_active"] else "inactive")
                    add("Proposed Status", "inactive (soft delete)")
            elif tool_name in {"adjust_stock", "transfer_stock"}:
                product = self._lookup_product(data, arguments.get("product_id", ""))
                add("Product", product["name"])
                add("SKU", product["sku"])
                if tool_name == "adjust_stock":
                    warehouse_id = arguments.get("warehouse_id", "")
                    add("Warehouse", warehouse_id)
                    stock = self._stock_row(data, product["product_id"], warehouse_id)
                    add("Current On Hand", stock["quantity_on_hand"] if stock else 0)
                    add("Quantity Change", arguments.get("quantity_change"))
                    add("Reason", arguments.get("reason", ""))
                else:
                    add("From Warehouse", arguments.get("from_warehouse_id", ""))
                    add("To Warehouse", arguments.get("to_warehouse_id", ""))
                    add("Quantity", arguments.get("quantity"))
                    source = self._stock_row(
                        data, product["product_id"], arguments.get("from_warehouse_id", "")
                    )
                    add("Available At Source", (
                        source["quantity_on_hand"] - source["quantity_reserved"]
                        if source else 0
                    ))
            elif tool_name == "create_purchase_order":
                supplier = _require(
                    data["suppliers"], "supplier_id", arguments.get("supplier_id", ""), "Supplier"
                )
                add("Supplier", supplier["name"])
                add("Warehouse", arguments.get("warehouse_id", ""))
                lines = self._normalise_items(
                    data,
                    arguments.get("items", []),
                    price_field="unit_cost",
                    use_selling=False,
                )
                add("Line Items", len(lines))
                add("Order Total", f"BDT {sum(line['line_total'] for line in lines):,}")
            elif tool_name == "update_purchase_order":
                order = _require(
                    data["purchase_orders"],
                    "purchase_order_id",
                    arguments.get("purchase_order_id", ""),
                    "Purchase order",
                )
                add("Purchase Order", order["purchase_order_id"])
                add("Current Status", order["status"])
                add("Proposed Status", arguments.get("status") or order["status"])
                add("Total", f"BDT {order['total']:,}")
            elif tool_name == "receive_purchase_order":
                order = _require(
                    data["purchase_orders"],
                    "purchase_order_id",
                    arguments.get("purchase_order_id", ""),
                    "Purchase order",
                )
                add("Purchase Order", order["purchase_order_id"])
                add("Current Status", order["status"])
                add("Total", f"BDT {order['total']:,}")
                add("Warehouse", order["warehouse_id"])
            elif tool_name == "create_invoice":
                sale = _require(data["sales"], "sale_id", arguments.get("sale_id", ""), "Sale")
                add("Sale", sale["sale_id"])
                add("Customer", sale["customer_id"])
                add("Invoice Total", f"BDT {sale['total']:,}")
            elif tool_name == "record_payment":
                invoice = _require(
                    data["invoices"], "invoice_id", arguments.get("invoice_id", ""), "Invoice"
                )
                add("Invoice", invoice["invoice_id"])
                add("Customer", invoice["customer_id"])
                add("Invoice Total", f"BDT {invoice['total']:,}")
                add("Outstanding", f"BDT {invoice['balance_due']:,}")
                add("Payment Amount", f"BDT {int(arguments.get('amount', 0)):,}")
                add("Method", arguments.get("method", ""))
            elif tool_name in {"process_return", "create_return_request"}:
                if tool_name == "process_return":
                    record = _require(
                        data["returns"], "return_id", arguments.get("return_id", ""), "Return"
                    )
                else:
                    record = {
                        "return_id": "new request",
                        "sale_id": arguments.get("sale_id", ""),
                        "product_id": arguments.get("product_id", ""),
                        "quantity": arguments.get("quantity"),
                        "refund_amount": arguments.get("refund_amount") or 0,
                    }
                add("Return", record.get("return_id"))
                add("Sale", record.get("sale_id"))
                add("Product", record.get("product_id"))
                add("Quantity", record.get("quantity"))
                add("Refund Amount", f"BDT {int(record.get('refund_amount') or 0):,}")
            elif tool_name == "update_sale":
                sale = _require(
                    data["sales"], "sale_id", arguments.get("sale_id", ""), "Sale"
                )
                add("Sale", sale["sale_id"])
                add("Customer", sale["customer_id"])
                add("Current Status", sale["status"])
                add("Current Discount", f"BDT {sale['discount']:,}")
                add("Current Total", f"BDT {sale['total']:,}")
                if arguments.get("discount") is not None:
                    new_discount = int(arguments["discount"])
                    add("Proposed Discount", f"BDT {new_discount:,}")
                    if 0 <= new_discount <= sale["subtotal"]:
                        taxable = sale["subtotal"] - new_discount
                        projected = taxable + _tax(taxable)
                        add("Projected Total", f"BDT {projected:,}")
                    else:
                        warnings.append("Discount exceeds the sale subtotal.")
                add("Proposed Status", arguments.get("status") or sale["status"])
            elif tool_name == "cancel_sale":
                sale = _require(data["sales"], "sale_id", arguments.get("sale_id", ""), "Sale")
                add("Sale", sale["sale_id"])
                add("Customer", sale["customer_id"])
                add("Status", sale["status"])
                add("Total", f"BDT {sale['total']:,}")
            elif tool_name == "create_expense":
                add("Account", arguments.get("account_id", ""))
                add("Description", arguments.get("description", ""))
                add("Amount", f"BDT {int(arguments.get('amount', 0)):,}")
                add("Payment Method", arguments.get("payment_method", ""))
            elif tool_name == "create_customer":
                add("Name", arguments.get("name", ""))
                add("Type", arguments.get("customer_type", ""))
                add("Credit Limit", f"BDT {int(arguments.get('credit_limit') or 0):,}")
        except InventoryError as error:
            warnings.append(str(error))

        return {"summary": summary, "warnings": warnings}

    def record_hitl_decision(
        self,
        payload: dict,
        decision: dict,
        outcome: str,
        actor_id: str | None = None,
    ) -> dict:
        """Append an audit record for a human decision. Never executes a tool."""
        action = {
            "approve": "approval_granted",
            "edit": "approval_edited",
            "reject": "approval_rejected",
        }.get(decision.get("action"), "approval_unknown")
        with self.store.transaction() as data:
            actor = actor_id or "HUMAN_OPERATOR"
            if (
                actor != "HUMAN_OPERATOR"
                and _find(data["employees"], "employee_id", actor) is None
            ):
                actor = "HUMAN_OPERATOR"
            audit_id = self.store.next_id(
                data, "audit_log", "audit_id", "AUD-2026", width=3
            )
            record = {
                "audit_id": audit_id,
                "actor_id": actor,
                "action": action,
                "resource_type": "tool",
                "resource_id": payload.get("operation_id"),
                "timestamp": _now_timestamp(),
                "previous_value": {
                    "tool": payload.get("tool"),
                    "arguments": payload.get("arguments"),
                },
                "new_value": {
                    "decision": decision.get("action"),
                    "arguments": decision.get("arguments", payload.get("arguments")),
                    "outcome": outcome,
                    "reviewed_by": actor,
                },
                "result": (
                    "failed"
                    if outcome == "failed"
                    else "rejected"
                    if decision.get("action") == "reject"
                    else "success"
                ),
                "reason": decision.get("comment", ""),
            }
            data["audit_log"].append(record)
            if len(data["audit_log"]) > self.audit_log_limit:
                data["audit_log"] = data["audit_log"][-self.audit_log_limit:]
            return {"audit": record}

    def describe_employee(self, employee_id: str) -> str:
        """Human-readable reviewer label, or the fallback actor name."""
        data = self.store.snapshot()
        row = _find(data["employees"], "employee_id", employee_id)
        if row is None:
            return "HUMAN_OPERATOR"
        return f"{row['name']} ({employee_id})"

    # =====================================================================
    # internals
    # =====================================================================

    def _lookup_product(self, data: dict, identifier: str) -> dict:
        if not identifier:
            raise InventoryError("product_id is required.")
        product = _find(data["products"], "product_id", identifier) or _find(
            data["products"], "sku", identifier
        )
        if product is None:
            raise InventoryError(f"Product not found: {identifier}.")
        return product

    def _decorate_product(self, data: dict, product: dict) -> dict:
        category = _find(data["categories"], "category_id", product["category_id"])
        supplier = _find(data["suppliers"], "supplier_id", product["supplier_id"])
        unit = _find(data["units"], "unit_id", product["unit_id"])
        return {
            **product,
            "category_name": category["name"] if category else "",
            "supplier_name": supplier["name"] if supplier else "",
            "unit_symbol": unit["symbol"] if unit else "",
            "available_quantity": self._available(data, product["product_id"]),
        }

    def _decorate_stock(self, data: dict, stock: dict) -> dict:
        warehouse = _find(data["warehouses"], "warehouse_id", stock["warehouse_id"])
        product = _find(data["products"], "product_id", stock["product_id"])
        return {
            **stock,
            "warehouse_name": warehouse["name"] if warehouse else "",
            "product_name": product["name"] if product else "",
            "sku": product["sku"] if product else "",
            "available_quantity": stock["quantity_on_hand"] - stock["quantity_reserved"],
        }

    def _decorate_sale(self, data: dict, sale: dict) -> dict:
        customer = _find(data["customers"], "customer_id", sale["customer_id"])
        employee = _find(data["employees"], "employee_id", sale["sales_employee_id"])
        return {
            **sale,
            "customer_name": customer["name"] if customer else "",
            "sales_employee_name": employee["name"] if employee else "",
        }

    def _decorate_invoice(self, data: dict, invoice: dict) -> dict:
        customer = _find(data["customers"], "customer_id", invoice["customer_id"])
        return {
            **invoice,
            "customer_name": customer["name"] if customer else "",
        }

    def _decorate_purchase_order(self, data: dict, order: dict) -> dict:
        supplier = _find(data["suppliers"], "supplier_id", order["supplier_id"])
        return {
            **order,
            "supplier_name": supplier["name"] if supplier else "",
        }

    def _decorate_expense(self, data: dict, expense: dict) -> dict:
        account = _find(data["accounts"], "account_id", expense["account_id"])
        return {
            **expense,
            "account_name": account["name"] if account else "",
        }

    def _decorate_approval(self, data: dict, approval: dict) -> dict:
        requester = _find(data["employees"], "employee_id", approval["requested_by"])
        assignee = _find(data["employees"], "employee_id", approval["assigned_to"])
        return {
            **approval,
            "requested_by_name": requester["name"] if requester else "",
            "assigned_to_name": assignee["name"] if assignee else "",
        }

    def _category_scope(self, categories: list[dict], category_id: str) -> set[str]:
        scope = {category_id}
        changed = True
        while changed:
            changed = False
            for row in categories:
                parent = row.get("parent_category_id")
                if parent in scope and row["category_id"] not in scope:
                    scope.add(row["category_id"])
                    changed = True
        return scope

    def _available(
        self, data: dict, product_id: str, warehouse_id: str | None = None
    ) -> int:
        return sum(
            row["quantity_on_hand"] - row["quantity_reserved"]
            for row in data["stock"]
            if row["product_id"] == product_id
            and (warehouse_id is None or row["warehouse_id"] == warehouse_id)
        )

    def _product_stock(self, data: dict, product_id: str) -> list[dict]:
        return [
            self._decorate_stock(data, row)
            for row in data["stock"]
            if row["product_id"] == product_id
        ]

    def _stock_row(
        self, data: dict, product_id: str, warehouse_id: str
    ) -> dict | None:
        return _find(
            [
                row
                for row in data["stock"]
                if row["product_id"] == product_id
                and row["warehouse_id"] == warehouse_id
            ],
            "product_id",
            product_id,
        )

    def _create_stock_row(self, data: dict, product_id: str, warehouse_id: str) -> dict:
        stock_id = self.store.next_id(data, "stock", "stock_id", "STK", width=4)
        row = {
            "stock_id": stock_id,
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "quantity_on_hand": 0,
            "quantity_reserved": 0,
            "updated_at": _now_timestamp(),
        }
        data["stock"].append(row)
        return row

    def _add_movement(
        self,
        data: dict,
        product_id: str,
        warehouse_id: str,
        movement_type: str,
        quantity_change: int,
        reference: str,
        movement_date: str,
        performed_by: str,
        notes: str,
    ) -> dict:
        movement_id = self.store.next_id(
            data, "stock_movements", "movement_id", "MOV", width=4
        )
        movement = {
            "movement_id": movement_id,
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "movement_type": movement_type,
            "quantity_change": quantity_change,
            "reference": reference,
            "movement_date": movement_date,
            "performed_by": performed_by,
            "notes": notes,
        }
        data["stock_movements"].append(movement)
        return movement

    def _normalise_items(
        self, data: dict, items: list[dict], *, price_field: str, use_selling: bool
    ) -> list[dict]:
        if not isinstance(items, list) or not items:
            raise InventoryError("items must be a non-empty list.")
        lines = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise InventoryError(f"items[{index}] must be an object.")
            product = self._lookup_product(data, str(item.get("product_id", "")))
            quantity = _positive(item.get("quantity"), f"items[{index}].quantity")
            raw_price = item.get(price_field)
            if raw_price is None:
                price = (
                    product["selling_price"] if use_selling else product["purchase_price"]
                )
            else:
                price = _non_negative(raw_price, f"items[{index}].{price_field}")
            lines.append(
                {
                    "product_id": product["product_id"],
                    "product_name": product["name"],
                    "quantity": quantity,
                    price_field: price,
                    "line_total": quantity * price,
                }
            )
        return lines

    def _reserve_and_deduct_sale_stock(
        self, data: dict, sale: dict, items: list[dict]
    ) -> None:
        for item in items:
            stock = self._stock_row(
                data, item["product_id"], sale["warehouse_id"]
            )
            available = (
                stock["quantity_on_hand"] - stock["quantity_reserved"]
                if stock else 0
            )
            if available < item["quantity"]:
                raise InventoryError(
                    f"Insufficient stock for {item['product_id']} at "
                    f"{sale['warehouse_id']}: {available} available, "
                    f"{item['quantity']} required."
                )
        for item in items:
            stock = self._stock_row(data, item["product_id"], sale["warehouse_id"])
            stock["quantity_on_hand"] -= item["quantity"]
            stock["updated_at"] = _now_timestamp()
            self._add_movement(
                data,
                item["product_id"],
                sale["warehouse_id"],
                "sale",
                -item["quantity"],
                sale["sale_id"],
                sale["sale_date"],
                sale["sales_employee_id"],
                "Goods issued when the sale was confirmed.",
            )

    def _cancel_sale_locked(
        self, data: dict, sale: dict, items: list[dict], reason: str
    ) -> None:
        if sale["status"] == "cancelled":
            return
        invoice = _find(data["invoices"], "sale_id", sale["sale_id"])
        if invoice is not None and invoice["amount_paid"] > 0:
            raise InventoryError(
                "The sale has recorded payments and cannot be cancelled."
            )
        if sale["status"] in {"confirmed", "invoiced", "partially_paid", "paid"}:
            for item in items:
                stock = self._stock_row(
                    data, item["product_id"], sale["warehouse_id"]
                )
                if stock is None:
                    stock = self._create_stock_row(
                        data, item["product_id"], sale["warehouse_id"]
                    )
                stock["quantity_on_hand"] += item["quantity"]
                stock["updated_at"] = _now_timestamp()
                self._add_movement(
                    data,
                    item["product_id"],
                    sale["warehouse_id"],
                    "stock_adjustment",
                    item["quantity"],
                    f"ADJ-{sale['sale_id']}",
                    _now_date(),
                    "EMP-004",
                    f"Stock restored because the sale was cancelled: {reason}",
                )
        if invoice is not None:
            invoice["status"] = "cancelled"
            invoice["balance_due"] = 0
            self._recompute_customer_balance(data, sale["customer_id"])
        sale["status"] = "cancelled"

    def _recompute_customer_balance(self, data: dict, customer_id: str) -> int:
        balance = sum(
            row["balance_due"]
            for row in data["invoices"]
            if row["customer_id"] == customer_id
            and row["status"] in OPEN_INVOICE_STATUSES
        )
        customer = _find(data["customers"], "customer_id", customer_id)
        if customer is not None:
            customer["outstanding_balance"] = balance
        return balance

    def _customer_balance(self, data: dict, customer_id: str) -> int:
        return sum(
            row["balance_due"]
            for row in data["invoices"]
            if row["customer_id"] == customer_id
            and row["status"] in OPEN_INVOICE_STATUSES
        )
