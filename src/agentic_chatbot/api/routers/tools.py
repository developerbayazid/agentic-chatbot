"""Tool catalog endpoints.

A read-only view of the tools the assistant can actually call. This exists so the
UI can show what is available instead of a placeholder, and it deliberately
exposes only names and descriptions — never arguments, prompts, or internals.

Listing is not a capability: execution still happens exclusively inside a graph
turn, and sensitive tools still require human approval.
"""

from __future__ import annotations

import threading
from typing import Any

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
    inventory_names = _inventory_tool_names(container)

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


# Cached on the container rather than in a module-level dict: the container owns
# the inventory service, so the cache lifetime matches it exactly and a replaced
# container (tests, reloads) cannot inherit a stale entry.
_CACHE_ATTRIBUTE = "_tool_catalog_inventory_names"
_CACHE_LOCK = threading.Lock()


def _inventory_tool_names(container: Any) -> set[str]:
    """Names of tools that come from the inventory service.

    `create_inventory_tools` constructs 54 Pydantic schemas — about 150 ms — and
    the result cannot change while the process runs, so it is computed once.
    """
    inventory_service = getattr(container, "inventory_service", None)

    if inventory_service is None:
        return set()

    cached = getattr(container, _CACHE_ATTRIBUTE, None)

    if cached is not None:
        return cached

    with _CACHE_LOCK:
        # Re-check under the lock: two concurrent first requests would otherwise
        # both build the schemas.
        cached = getattr(container, _CACHE_ATTRIBUTE, None)

        if cached is None:
            from agentic_chatbot.inventory.tools import create_inventory_tools

            cached = {tool.name for tool in create_inventory_tools(inventory_service)}
            setattr(container, _CACHE_ATTRIBUTE, cached)

        return cached
