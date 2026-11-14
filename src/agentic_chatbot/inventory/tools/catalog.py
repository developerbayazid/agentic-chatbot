"""Product and category tools."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from agentic_chatbot.inventory.service import InventoryService
from agentic_chatbot.inventory.tools._helpers import call, operation_id


def create_catalog_tools(service: InventoryService) -> list[BaseTool]:
    @tool
    def list_products(
        category_id: str = "", active_only: bool = True, limit: int = 50
    ) -> str:
        """List inventory products with prices, supplier, and available quantity.

        Use when the user asks what products exist, wants a catalogue or price
        overview, or asks for products in a category (child categories included).
        For a single known product use get_product; for keyword lookup use
        search_products.
        """
        return call(service.list_products, category_id, active_only, limit)

    @tool
    def get_product(product_id: str) -> str:
        """Get one product by product ID or SKU, including stock by warehouse.

        Use when the user names a specific product, SKU, or product ID and wants
        its details, price, or stock position.
        """
        return call(service.get_product, product_id)

    @tool
    def search_products(
        query: str, category_id: str = "", active_only: bool = True
    ) -> str:
        """Search products by name, SKU, barcode, or description.

        Use when the user describes a product without naming an exact ID, for
        example "laptops", "routers", or "wireless mouse". This returns catalogue
        matches, not a stock answer: follow with check_product_availability or
        get_stock when the question is about quantity.
        """
        return call(service.search_products, query, category_id, active_only)

    @tool
    def create_product(
        sku: str,
        name: str,
        category_id: str,
        unit_id: str,
        supplier_id: str,
        purchase_price: float,
        selling_price: float,
        description: str,
        reorder_level: int = 0,
        barcode: str = "",
    ) -> str:
        """Create a product with a unique SKU, category, unit, and supplier.

        Use only when the user explicitly asks to add a new product. Validate the
        category, unit, and supplier IDs first with list_categories,
        list_suppliers, and get_product.
        """
        return call(
            service.create_product,
            sku,
            name,
            category_id,
            unit_id,
            supplier_id,
            purchase_price,
            selling_price,
            description,
            reorder_level,
            barcode,
        )

    @tool
    def update_product(
        product_id: str,
        name: str | None = None,
        category_id: str | None = None,
        unit_id: str | None = None,
        supplier_id: str | None = None,
        description: str | None = None,
        purchase_price: float | None = None,
        selling_price: float | None = None,
        reorder_level: int | None = None,
        is_active: bool | None = None,
        *,
        config: RunnableConfig,
    ) -> str:
        """Update product fields such as the selling price or reorder level.

        Use when the user asks to change a product's price, name, category,
        supplier, or reorder level. Look the product up first. This is a
        sensitive operation: the graph pauses for human approval before executing,
        and the human may approve, edit the arguments, or reject.
        """
        return call(
            service.update_product,
            product_id,
            name,
            category_id,
            unit_id,
            supplier_id,
            description,
            purchase_price,
            selling_price,
            reorder_level,
            is_active,
            operation_id=operation_id(config),
        )

    @tool
    def deactivate_product(
        product_id: str,
        reason: str = "",
        *,
        config: RunnableConfig,
    ) -> str:
        """Deactivate (soft-delete) a product while keeping its history.

        Use when the user asks to delete or remove a product. Products referenced
        by sales, purchase orders, or stock movements are never hard-deleted; they
        are marked inactive. This sensitive operation requires human approval.
        """
        return call(
            service.deactivate_product,
            product_id,
            reason,
            operation_id=operation_id(config),
        )

    @tool
    def list_categories(active_only: bool = True) -> str:
        """List product categories, including parent/child links and product counts.

        Use when the user asks about categories or you need a category_id before
        creating or filtering a product.
        """
        return call(service.list_categories, active_only)

    @tool
    def create_category(
        name: str,
        description: str,
        parent_category_id: str = "",
    ) -> str:
        """Create a product category, optionally under a parent category.

        Use when the user asks to add a new category. Use list_categories first to
        find a valid parent_category_id.
        """
        return call(service.create_category, name, description, parent_category_id)

    @tool
    def update_category(
        category_id: str,
        name: str | None = None,
        description: str | None = None,
        parent_category_id: str | None = None,
        is_active: bool | None = None,
    ) -> str:
        """Update a category's name, description, parent, or active flag."""
        return call(
            service.update_category,
            category_id,
            name,
            description,
            parent_category_id,
            is_active,
        )

    return [
        list_products,
        get_product,
        search_products,
        create_product,
        update_product,
        deactivate_product,
        list_categories,
        create_category,
        update_category,
    ]
