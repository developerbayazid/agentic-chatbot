"""Stock tools."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from agentic_chatbot.inventory.service import InventoryService
from agentic_chatbot.inventory.tools._helpers import call, operation_id


def create_stock_tools(service: InventoryService) -> list[BaseTool]:
    @tool
    def get_stock(product_id: str = "", warehouse_id: str = "") -> str:
        """Show stock rows with on-hand, reserved, and available quantities.

        Use when the user asks about stock levels, warehouse inventory, or what is
        reserved. available_quantity = quantity_on_hand - quantity_reserved.
        """
        return call(service.get_stock, product_id, warehouse_id)

    @tool
    def check_low_stock(warehouse_id: str = "") -> str:
        """List products at or below their reorder level, including out-of-stock items.

        Use when the user asks which products are running low, need reordering, or
        are out of stock. Pass a warehouse_id to check one location.
        """
        return call(service.check_low_stock, warehouse_id)

    @tool
    def check_product_availability(product_id: str, warehouse_id: str = "") -> str:
        """Check how many units of a product are available to sell or transfer.

        Use when the user asks "how many laptops are available?", whether an item
        is in stock, or whether a quantity can be fulfilled. If you only know the
        product name or SKU, call search_products first to get the product_id,
        then call this tool. Do not infer availability from a product search.
        """
        return call(service.check_product_availability, product_id, warehouse_id)

    @tool
    def adjust_stock(
        product_id: str,
        warehouse_id: str,
        quantity_change: int,
        reason: str,
        performed_by: str,
        *,
        config: RunnableConfig,
    ) -> str:
        """Adjust stock by a signed quantity and record a stock movement.

        Use when the user asks to increase or decrease stock, write off damaged
        units, or correct a count. quantity_change must be non-zero; a negative
        value is a reduction. This sensitive operation requires human approval and
        cannot make available quantity negative.
        """
        return call(
            service.adjust_stock,
            product_id,
            warehouse_id,
            quantity_change,
            reason,
            performed_by,
            operation_id=operation_id(config),
        )

    @tool
    def transfer_stock(
        product_id: str,
        from_warehouse_id: str,
        to_warehouse_id: str,
        quantity: int,
        performed_by: str,
        reason: str = "",
        *,
        config: RunnableConfig,
    ) -> str:
        """Move stock between warehouses and record transfer-out/transfer-in movements.

        Use when the user asks to transfer stock from one warehouse to another.
        The source must have enough available quantity. Requires human approval.
        """
        return call(
            service.transfer_stock,
            product_id,
            from_warehouse_id,
            to_warehouse_id,
            quantity,
            performed_by,
            reason,
            operation_id=operation_id(config),
        )

    @tool
    def get_stock_movements(
        product_id: str = "",
        warehouse_id: str = "",
        movement_type: str = "",
        limit: int = 50,
    ) -> str:
        """List historical stock movements, newest first.

        Use when the user asks about stock history, adjustments, transfers,
        receipts, sales, or returns for a product or warehouse. Valid
        movement_type values are purchase_receipt, sale, stock_adjustment,
        transfer_in, transfer_out, and sales_return.
        """
        return call(
            service.get_stock_movements,
            product_id,
            warehouse_id,
            movement_type,
            limit,
        )

    return [
        get_stock,
        check_low_stock,
        check_product_availability,
        adjust_stock,
        transfer_stock,
        get_stock_movements,
    ]
