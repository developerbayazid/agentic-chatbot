"""Sensitive-tool metadata for the inventory demo.

Tool execution policy lives in ``graph/approval.py``; this module only tells the
composition root which inventory tools require a human decision.
"""

from __future__ import annotations

# Tool name -> human-facing action title shown in the approval panel.
SENSITIVE_TOOLS: dict[str, str] = {
    "update_product": "Update Product",
    "deactivate_product": "Deactivate Product",
    "update_customer": "Update Customer",
    "adjust_stock": "Adjust Stock",
    "transfer_stock": "Transfer Stock",
    "create_sale": "Create Sale",
    "update_sale": "Update Sale",
    "cancel_sale": "Cancel Sale",
    "create_invoice": "Create Invoice",
    "record_payment": "Record Payment",
    "create_purchase_order": "Create Purchase Order",
    "update_purchase_order": "Update Purchase Order",
    "receive_purchase_order": "Receive Purchase Order",
    "create_expense": "Create Expense",
    "process_return": "Approve / Process Return",
}
