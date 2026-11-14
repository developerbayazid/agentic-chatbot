"""Sales, invoice, and payment tools."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from agentic_chatbot.inventory.service import InventoryService
from agentic_chatbot.inventory.tools._helpers import call, operation_id


def create_sales_tools(service: InventoryService) -> list[BaseTool]:
    @tool
    def list_sales(
        customer_id: str = "",
        employee_id: str = "",
        status: str = "",
        limit: int = 50,
    ) -> str:
        """List sales with status, totals, customer, and sales employee.

        Use when the user asks to see sales, orders, or revenue by customer or
        employee. For one sale use get_sale.
        """
        return call(service.list_sales, customer_id, employee_id, status, limit)

    @tool
    def get_sale(sale_id: str) -> str:
        """Get one sale with its line items and related invoice."""
        return call(service.get_sale, sale_id)

    @tool
    def create_sale(
        customer_id: str,
        sales_employee_id: str,
        warehouse_id: str,
        items: list[dict],
        discount: float = 0,
        status: str = "pending_approval",
        *,
        config: RunnableConfig,
    ) -> str:
        """Create a draft or pending-approval sale with line items.

        items is a list such as [{"product_id": "PRD-1001", "quantity": 2,
        "unit_price": 89500}]. unit_price is optional and defaults to the product
        selling price. Stock is not deducted until the sale is confirmed. Detect
        duplicate requests before creating a second sale. Requires human approval.
        """
        return call(
            service.create_sale,
            customer_id,
            sales_employee_id,
            warehouse_id,
            items,
            discount,
            status,
            operation_id=operation_id(config),
        )

    @tool
    def update_sale(
        sale_id: str,
        status: str | None = None,
        discount: float | None = None,
        *,
        config: RunnableConfig,
    ) -> str:
        """Confirm or cancel a sale, or change its discount before confirmation.

        Confirming deducts stock and writes sale movements. Invoicing is done with
        create_invoice, not here. Requires human approval.
        """
        return call(
            service.update_sale,
            sale_id,
            status,
            discount,
            operation_id=operation_id(config),
        )

    @tool
    def cancel_sale(
        sale_id: str, reason: str = "", *, config: RunnableConfig
    ) -> str:
        """Cancel a sale and restore stock if it had already been confirmed.

        Sales with recorded payments cannot be cancelled. Requires human approval.
        """
        return call(
            service.cancel_sale, sale_id, reason, operation_id=operation_id(config)
        )

    @tool
    def get_sales_by_customer(customer_id: str) -> str:
        """List every sale for one customer, newest first."""
        return call(service.get_sales_by_customer, customer_id)

    @tool
    def get_sales_by_employee(employee_id: str) -> str:
        """List every sale attributed to one sales employee."""
        return call(service.get_sales_by_employee, employee_id)

    @tool
    def list_invoices(
        customer_id: str = "", status: str = "", limit: int = 50
    ) -> str:
        """List invoices with totals, paid amounts, balances, and status.

        Use when the user asks for invoices, billing status, or paid/unpaid
        records. For open balances use get_outstanding_invoices.
        """
        return call(service.list_invoices, customer_id, status, limit)

    @tool
    def get_invoice(invoice_id: str) -> str:
        """Get one invoice with its payment history."""
        return call(service.get_invoice, invoice_id)

    @tool
    def create_invoice(
        sale_id: str, due_days: int = 30, *, config: RunnableConfig
    ) -> str:
        """Create an unpaid invoice for a confirmed sale.

        Only confirmed sales can be invoiced, and each sale can have one invoice.
        Requires human approval.
        """
        return call(
            service.create_invoice, sale_id, due_days, operation_id=operation_id(config)
        )

    @tool
    def record_payment(
        invoice_id: str,
        amount: float,
        method: str,
        reference: str = "",
        payment_date: str = "",
        *,
        config: RunnableConfig,
    ) -> str:
        """Record a payment against an open invoice and update balances.

        method must be cash, bank_transfer, mobile_banking, or card. The amount
        must not exceed the invoice balance_due. This updates the invoice, the
        customer's outstanding balance, and the sale status. Requires human
        approval; duplicate payments are rejected by balance validation.
        """
        return call(
            service.record_payment,
            invoice_id,
            amount,
            method,
            reference,
            payment_date,
            operation_id=operation_id(config),
        )

    @tool
    def get_outstanding_invoices(customer_id: str = "") -> str:
        """List unpaid, partially paid, and overdue invoices with balances.

        Use when the user asks "show all unpaid invoices", what is overdue, or
        what a customer still owes.
        """
        return call(service.get_outstanding_invoices, customer_id)

    @tool
    def get_customer_balance(customer_id: str) -> str:
        """Show a customer's outstanding balance, credit limit, and available credit.

        Use when the user asks "how much does customer X owe?" or about a
        customer's credit position.
        """
        return call(service.get_customer_balance, customer_id)

    return [
        list_sales,
        get_sale,
        create_sale,
        update_sale,
        cancel_sale,
        get_sales_by_customer,
        get_sales_by_employee,
        list_invoices,
        get_invoice,
        create_invoice,
        record_payment,
        get_outstanding_invoices,
        get_customer_balance,
    ]
