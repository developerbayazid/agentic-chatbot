"""Inventory tool factories, grouped by business area."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from agentic_chatbot.inventory.service import InventoryService
from agentic_chatbot.inventory.tools.catalog import create_catalog_tools
from agentic_chatbot.inventory.tools.finance import create_finance_tools
from agentic_chatbot.inventory.tools.parties import create_party_tools
from agentic_chatbot.inventory.tools.procurement import create_procurement_tools
from agentic_chatbot.inventory.tools.sales import create_sales_tools
from agentic_chatbot.inventory.tools.stock import create_stock_tools
from agentic_chatbot.inventory.tools.workflows import create_workflow_tools


def create_inventory_tools(service: InventoryService) -> list[BaseTool]:
    """Return every inventory tool bound to one service instance."""
    return [
        *create_catalog_tools(service),
        *create_stock_tools(service),
        *create_party_tools(service),
        *create_sales_tools(service),
        *create_procurement_tools(service),
        *create_finance_tools(service),
        *create_workflow_tools(service),
    ]


__all__ = ["create_inventory_tools"]
