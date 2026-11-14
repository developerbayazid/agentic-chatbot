"""Accounting and expense tools."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from agentic_chatbot.inventory.service import InventoryService
from agentic_chatbot.inventory.tools._helpers import call, operation_id


def create_finance_tools(service: InventoryService) -> list[BaseTool]:
    @tool
    def list_accounts(account_type: str = "") -> str:
        """List chart-of-accounts entries, optionally filtered by account type.

        account_type is one of Asset, Liability, Equity, Revenue, or Expense.
        Use this to find a valid account_id before creating an expense.
        """
        return call(service.list_accounts, account_type)

    @tool
    def get_account(account: str) -> str:
        """Get one account by account_id or account_code, plus related journal entries."""
        return call(service.get_account, account)

    @tool
    def list_expenses(status: str = "", limit: int = 50) -> str:
        """List expenses with account, amount, submitter, and approval status.

        Status values are draft, pending_approval, approved, rejected, and paid.
        Use status="pending_approval" to review pending expenses.
        """
        return call(service.list_expenses, status, limit)

    @tool
    def create_expense(
        account_id: str,
        description: str,
        amount: float,
        payment_method: str,
        submitted_by: str,
        expense_date: str = "",
        status: str = "pending_approval",
        *,
        config: RunnableConfig,
    ) -> str:
        """Create a draft or pending-approval expense against an Expense account.

        payment_method must be cash, bank_transfer, mobile_banking, or card.
        Requires human approval before the expense is considered authorised.
        """
        return call(
            service.create_expense,
            account_id,
            description,
            amount,
            payment_method,
            submitted_by,
            expense_date,
            status,
            operation_id=operation_id(config),
        )

    @tool
    def get_financial_summary() -> str:
        """Summarise receivables, payables, inventory value, revenue, and expenses.

        Use when the user asks for a high-level financial position or business
        summary. Amounts are in BDT.
        """
        return call(service.get_financial_summary)

    @tool
    def get_sales_summary(period: str = "") -> str:
        """Summarise sales totals by status and employee for all time or a month.

        period uses YYYY-MM, for example 2026-03. Leave empty for all sales.
        """
        return call(service.get_sales_summary, period)

    return [
        list_accounts,
        get_account,
        list_expenses,
        create_expense,
        get_financial_summary,
        get_sales_summary,
    ]
