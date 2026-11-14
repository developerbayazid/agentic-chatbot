"""Customer and supplier tools."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from agentic_chatbot.inventory.service import InventoryService
from agentic_chatbot.inventory.tools._helpers import call, operation_id


def create_party_tools(service: InventoryService) -> list[BaseTool]:
    @tool
    def list_customers(active_only: bool = True, limit: int = 50) -> str:
        """List customers with type, contact details, credit limit, and outstanding balance.

        Use when the user asks for customers or needs a customer_id.
        """
        return call(service.list_customers, active_only, limit)

    @tool
    def get_customer(customer_id: str) -> str:
        """Get one customer with open invoices, sale count, and outstanding balance.

        Use when the user names a customer and asks about their account.
        """
        return call(service.get_customer, customer_id)

    @tool
    def search_customers(query: str, active_only: bool = True) -> str:
        """Search customers by name, ID, email, phone, or contact person."""
        return call(service.search_customers, query, active_only)

    @tool
    def create_customer(
        name: str,
        customer_type: str,
        email: str,
        phone: str,
        billing_address: str,
        shipping_address: str,
        contact_person: str = "",
        credit_limit: float = 0,
    ) -> str:
        """Create an individual or business customer with a credit limit.

        customer_type must be "individual" or "business". Use when the user asks
        to add a new customer.
        """
        return call(
            service.create_customer,
            name,
            customer_type,
            email,
            phone,
            billing_address,
            shipping_address,
            contact_person,
            credit_limit,
        )

    @tool
    def update_customer(
        customer_id: str,
        name: str | None = None,
        contact_person: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        billing_address: str | None = None,
        shipping_address: str | None = None,
        credit_limit: float | None = None,
        is_active: bool | None = None,
        *,
        config: RunnableConfig,
    ) -> str:
        """Update customer contact details, addresses, credit limit, or active flag.

        Use when the user asks to change a customer's credit limit or details.
        Sensitive operation: the graph pauses for human approval first.
        """
        return call(
            service.update_customer,
            customer_id,
            name,
            contact_person,
            email,
            phone,
            billing_address,
            shipping_address,
            credit_limit,
            is_active,
            operation_id=operation_id(config),
        )

    @tool
    def list_suppliers(active_only: bool = True, limit: int = 50) -> str:
        """List suppliers with contact details, payment terms, and outstanding balance.

        Use when the user asks for suppliers or needs a supplier_id.
        """
        return call(service.list_suppliers, active_only, limit)

    @tool
    def get_supplier(supplier_id: str) -> str:
        """Get one supplier with its products and purchase-order count."""
        return call(service.get_supplier, supplier_id)

    @tool
    def search_suppliers(query: str, active_only: bool = True) -> str:
        """Search suppliers by name, ID, email, phone, or contact person."""
        return call(service.search_suppliers, query, active_only)

    return [
        list_customers,
        get_customer,
        search_customers,
        create_customer,
        update_customer,
        list_suppliers,
        get_supplier,
        search_suppliers,
    ]
