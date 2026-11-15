"""Tool catalog endpoints.

A read-only view of the tools the assistant can actually call. This exists so the
UI can show what is available instead of a placeholder, and it deliberately
exposes only names and descriptions — never arguments, prompts, or internals.

Listing is not a capability: execution still happens exclusively inside a graph
turn, and sensitive tools still require human approval.
"""

from __future__ import annotations

from fastapi import APIRouter

from agentic_chatbot.api.dependencies import ContainerDep, CurrentUserDep
from agentic_chatbot.api.schemas import ToolInfo, ToolListResponse
from agentic_chatbot.inventory.approvals import SENSITIVE_TOOLS

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])

# Tool groups, derived from the registry rather than duplicated by hand.
_STATIC_HINTS = {
    "calculator": "Math",
    "get_current_time": "Utility",
    "web_search": "Web",
    "fetch_url": "Web",
    "get_news": "Web",
    "get_weather": "Web",
    "get_stock_price": "Finance",
    "convert_currency": "Finance",
    "send_email": "Communication",
    "send_slack_message": "Communication",
    "create_calendar_event": "Calendar",
    "list_calendar_events": "Calendar",
    "translate_text": "Text",
    "find_recipe": "Lifestyle",
    "get_holidays": "Lifestyle",
    "track_package": "Utility",
}

_NOTE_TOOLS = {"save_note", "list_notes", "search_notes", "delete_note"}
_DOCUMENT_TOOLS = {"search_documents", "list_documents"}


def _category(name: str, inventory_names: set[str]) -> str:
    if name in inventory_names:
        return "Inventory (demo)"

    if name in _NOTE_TOOLS:
        return "Notes"

    if name in _DOCUMENT_TOOLS:
        return "Documents"

    return _STATIC_HINTS.get(name, "Utility")


@router.get("", response_model=ToolListResponse)
def list_tools(user: CurrentUserDep, container: ContainerDep) -> ToolListResponse:
    """Every tool the assistant can call, grouped and marked for approval.

    ``requires_approval`` reflects the server's real sensitive-tool policy, not a
    UI assumption, so the list cannot drift from the gate that enforces it.
    """
    inventory_service = container.inventory_service
    inventory_names: set[str] = set()

    if inventory_service is not None:
        from agentic_chatbot.inventory.tools import create_inventory_tools

        inventory_names = {tool.name for tool in create_inventory_tools(inventory_service)}

    tools = [
        ToolInfo(
            name=tool.name,
            description=(tool.description or "").strip().split("\n")[0][:300],
            category=_category(tool.name, inventory_names),
            requires_approval=tool.name in SENSITIVE_TOOLS,
        )
        for tool in container.tools
    ]
    tools.sort(key=lambda item: (item.category, item.name))

    return ToolListResponse(count=len(tools), tools=tools)
