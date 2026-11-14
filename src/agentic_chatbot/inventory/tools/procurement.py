"""Purchase order tools."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from agentic_chatbot.inventory.service import InventoryService
from agentic_chatbot.inventory.tools._helpers import call, operation_id


def create_procurement_tools(service: InventoryService) -> list[BaseTool]:
    @tool
    def list_purchase_orders(
        supplier_id: str = "", status: str = "", limit: int = 50
    ) -> str:
        """List purchase orders with supplier, status, and total.

        Use when the user asks about purchase orders or pending procurement. Status
        values include pending_approval, approved, ordered, received, and
        cancelled.
        """
        return call(service.list_purchase_orders, supplier_id, status, limit)

    @tool
    def get_purchase_order(purchase_order_id: str) -> str:
        """Get one purchase order with line items and goods-receipt movements."""
        return call(service.get_purchase_order, purchase_order_id)

    @tool
    def create_purchase_order(
        supplier_id: str,
        warehouse_id: str,
        items: list[dict],
        created_by: str,
        expected_date: str = "",
        status: str = "pending_approval",
        *,
        config: RunnableConfig,
    ) -> str:
        """Create a draft or pending-approval purchase order with line items.

        items is a list such as [{"product_id": "PRD-1015", "quantity": 10,
        "unit_cost": 5300}]. unit_cost is optional and defaults to the product
        purchase price. Look up the supplier and products first. Requires human
        approval before the order can move to approved/ordered.
        """
        return call(
            service.create_purchase_order,
            supplier_id,
            warehouse_id,
            items,
            created_by,
            expected_date,
            status,
            operation_id=operation_id(config),
        )

    @tool
    def update_purchase_order(
        purchase_order_id: str,
        status: str | None = None,
        expected_date: str | None = None,
        *,
        config: RunnableConfig,
    ) -> str:
        """Approve, reject, order, or cancel a purchase order using valid transitions.

        Receiving goods is done with receive_purchase_order. Requires human
        approval.
        """
        return call(
            service.update_purchase_order,
            purchase_order_id,
            status,
            expected_date,
            operation_id=operation_id(config),
        )

    @tool
    def receive_purchase_order(
        purchase_order_id: str, *, config: RunnableConfig
    ) -> str:
        """Receive an approved/ordered purchase order into the destination warehouse.

        Increases stock, creates purchase_receipt movements, and marks the order
        received. The operation is idempotent per approval. Requires human approval.
        """
        return call(
            service.receive_purchase_order,
            purchase_order_id,
            operation_id=operation_id(config),
        )

    return [
        list_purchase_orders,
        get_purchase_order,
        create_purchase_order,
        update_purchase_order,
        receive_purchase_order,
    ]
