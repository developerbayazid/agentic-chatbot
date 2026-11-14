"""Return, approval, and HITL-adjacent tools."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from agentic_chatbot.inventory.service import InventoryService
from agentic_chatbot.inventory.tools._helpers import call, operation_id


def create_workflow_tools(service: InventoryService) -> list[BaseTool]:
    @tool
    def create_return_request(
        sale_id: str,
        product_id: str,
        quantity: int,
        reason: str,
        refund_amount: float | None = None,
    ) -> str:
        """Create a pending_review return request for a product on a sale.

        Use when the user asks to return goods or request a refund. The quantity
        cannot exceed the unreturned quantity on the sale. refund_amount defaults
        to quantity times the sale unit price.
        """
        return call(
            service.create_return_request,
            sale_id,
            product_id,
            quantity,
            reason,
            refund_amount,
        )

    @tool
    def get_return(return_id: str) -> str:
        """Get one return request with its original sale."""
        return call(service.get_return, return_id)

    @tool
    def list_returns(status: str = "", limit: int = 50) -> str:
        """List return requests, optionally filtered by status.

        Status values are pending_review, approved, rejected, and processed.
        """
        return call(service.list_returns, status, limit)

    @tool
    def process_return(
        return_id: str,
        decision: str = "approve",
        approver_id: str = "EMP-006",
        *,
        config: RunnableConfig,
    ) -> str:
        """Approve (restock and refund) or reject a pending return request.

        decision must be "approve" or "reject". Approving updates stock with a
        sales_return movement, records the refund, and marks the return processed.
        This is a sensitive operation and requires human approval through the graph
        interrupt; it must never be treated as pre-approved.
        """
        return call(
            service.process_return,
            return_id,
            decision,
            approver_id,
            operation_id=operation_id(config),
        )

    @tool
    def get_pending_approvals() -> str:
        """List business approvals waiting for a decision in the dataset.

        This covers seeded purchase-order, expense, discount, stock-adjustment,
        and return approvals. Live graph interrupts are approved through the CLI
        panel, not by calling a tool.
        """
        return call(service.get_pending_approvals)

    @tool
    def get_approval_details(approval_id: str) -> str:
        """Get one seeded approval with requester, assignee, and decision fields."""
        return call(service.get_approval_details, approval_id)

    @tool
    def get_approval_history(
        resource_type: str = "", resource_id: str = ""
    ) -> str:
        """Show completed approvals and related audit records.

        Optionally filter by resource_type (purchase_order, expense, sale, return,
        stock_movement) and resource_id.
        """
        return call(service.get_approval_history, resource_type, resource_id)

    return [
        create_return_request,
        get_return,
        list_returns,
        process_return,
        get_pending_approvals,
        get_approval_details,
        get_approval_history,
    ]
