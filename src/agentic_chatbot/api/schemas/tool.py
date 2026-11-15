"""Tool catalog schemas.

Read-only metadata for the tools the assistant can call. Descriptions are
truncated server-side: the tool docstrings guide the model and can be long, and
the UI only needs the first line.
"""

from __future__ import annotations

from agentic_chatbot.api.schemas.auth import StrictModel


class ToolInfo(StrictModel):
    name: str
    description: str
    category: str
    requires_approval: bool


class ToolListResponse(StrictModel):
    count: int
    tools: list[ToolInfo]
