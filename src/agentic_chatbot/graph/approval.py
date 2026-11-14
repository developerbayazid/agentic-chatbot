"""LangGraph node that pauses sensitive tool calls for human approval.

The node is deliberately generic: the container supplies the sensitive-tool
titles plus optional preview and decision-recording callbacks, so the graph
layer does not import the inventory package.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.types import interrupt

logger = logging.getLogger(__name__)

PreviewFn = Callable[[str, dict], dict]
RecordFn = Callable[[dict, dict, str], None]

STALE_APPROVAL = (
    "Error: this approval does not match the current proposal. "
    "The action was not executed; request a fresh approval."
)


def make_approval_token(
    tool_name: str, arguments: dict[str, Any], tool_call_id: str
) -> str:
    payload = json.dumps(
        {"tool": tool_name, "arguments": arguments, "tool_call_id": tool_call_id},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def pending_tool_calls(messages: Sequence[BaseMessage]) -> list[dict]:
    """Return tool calls from the newest AI message that have no ToolMessage yet."""
    answered = {
        getattr(message, "tool_call_id", None)
        for message in messages
        if isinstance(message, ToolMessage)
    }
    for message in reversed(messages):
        if isinstance(message, AIMessage) and getattr(message, "tool_calls", None):
            return [
                call
                for call in message.tool_calls
                if call.get("id") not in answered
            ]
    return []


def route_after_chat(
    state: dict, sensitive: dict[str, str]
) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "end"

    calls = getattr(messages[-1], "tool_calls", None) or []
    if not calls:
        return "end"

    if any(call.get("name") in sensitive for call in calls):
        return "approval"

    return "tools"


def route_after_approval(state: dict) -> str:
    return "approval" if pending_tool_calls(state.get("messages", [])) else "chat_node"


def _invoke_tool(
    tool: BaseTool,
    arguments: dict,
    config: RunnableConfig | None,
    op_id: str | None,
) -> str:
    run_config: dict[str, Any] = dict(config or {})
    configurable = dict(run_config.get("configurable") or {})
    if op_id:
        configurable["inventory_operation_id"] = op_id
    run_config["configurable"] = configurable

    try:
        return str(tool.invoke(arguments, run_config))
    except Exception as error:  # noqa: BLE001 - reported back to the model
        logger.debug("tool %s failed under approval", tool.name, exc_info=True)
        return f"Error: {error}"


def _clean_edited_arguments(tool: BaseTool, arguments: Any) -> dict:
    if not isinstance(arguments, dict):
        raise ValueError("Edited arguments must be a JSON object.")

    allowed = set(tool.args or {})
    if not allowed:
        return dict(arguments)

    return {key: value for key, value in arguments.items() if key in allowed}


def _schema_type(schema: Any) -> str:
    """Best-effort primitive type for a tool argument (handles Optional unions)."""
    if not isinstance(schema, dict):
        return ""
    if schema.get("type"):
        return str(schema["type"])
    for option in schema.get("anyOf") or ():
        if isinstance(option, dict) and option.get("type") not in (None, "null"):
            return str(option["type"])
    return ""


def create_approval_node(
    tools: Sequence[BaseTool],
    sensitive: dict[str, str],
    preview: PreviewFn | None = None,
    record: RecordFn | None = None,
):
    """Build the node that interrupts before sensitive tool execution."""
    tools_by_name = {tool.name: tool for tool in tools}

    def approval_node(state: dict, config: RunnableConfig):
        messages = state.get("messages", [])
        pending = pending_tool_calls(messages)

        if not pending:
            return {}

        call = pending[0]
        name = call.get("name", "")
        arguments = call.get("args") or {}
        call_id = call.get("id") or "missing-call-id"
        tool = tools_by_name.get(name)

        if tool is None:
            return {
                "messages": [
                    ToolMessage(
                        content=f"Error: unknown tool {name!r}.",
                        name=name,
                        tool_call_id=call_id,
                    )
                ]
            }

        if name not in sensitive:
            content = _invoke_tool(tool, arguments, config, None)
            return {
                "messages": [
                    ToolMessage(content=content, name=name, tool_call_id=call_id)
                ]
            }

        thread_id = str((config.get("configurable") or {}).get("thread_id") or "unknown")
        operation = f"{thread_id}:{call_id}"
        token = make_approval_token(name, arguments, call_id)

        details = {"summary": [], "warnings": []}
        if preview is not None:
            try:
                details = preview(name, arguments) or details
            except Exception:  # noqa: BLE001 - a preview must never block approval
                logger.debug("approval preview failed for %s", name, exc_info=True)

        schema = tool.args or {}
        editable_fields = list(schema)
        field_types = {
            field: _schema_type(schema.get(field, {})) for field in editable_fields
        }

        payload = {
            "kind": "approval_request",
            "tool": name,
            "title": sensitive.get(name, name.replace("_", " ").title()),
            "tool_call_id": call_id,
            "operation_id": operation,
            "arguments": arguments,
            "editable_fields": editable_fields,
            "field_types": field_types,
            "details": details.get("summary", []),
            "warnings": details.get("warnings", []),
            "approval_token": token,
            "requested_by": "AI Agent",
            "reason": "The agent requested a sensitive inventory operation.",
        }

        decision = interrupt(payload)

        if not isinstance(decision, dict):
            decision = {"action": "reject", "comment": "Invalid approval response."}

        action = decision.get("action")
        if action not in {"approve", "edit", "reject"}:
            action = "reject"
            decision = {
                "action": "reject",
                "comment": "Invalid approval response.",
            }

        if action in {"approve", "edit"} and decision.get("approval_token") != token:
            content = STALE_APPROVAL
            _record(record, payload, decision, "failed")
            return {
                "messages": [
                    ToolMessage(content=content, name=name, tool_call_id=call_id)
                ]
            }

        if action == "reject":
            comment = str(decision.get("comment") or "").strip()
            content = "Action rejected by the human reviewer. It was not executed."
            if comment:
                content = f"{content} Reason: {comment}"
            _record(record, payload, decision, "rejected")
            return {
                "messages": [
                    ToolMessage(content=content, name=name, tool_call_id=call_id)
                ]
            }

        final_arguments = arguments
        if action == "edit":
            try:
                final_arguments = _clean_edited_arguments(
                    tool, decision.get("arguments")
                )
            except ValueError as error:
                content = f"Error: {error}"
                _record(record, payload, decision, "failed")
                return {
                    "messages": [
                        ToolMessage(content=content, name=name, tool_call_id=call_id)
                    ]
                }

        content = _invoke_tool(tool, final_arguments, config, operation)
        outcome = "failed" if content.startswith("Error:") else "success"
        _record(record, payload, decision, outcome)

        return {
            "messages": [ToolMessage(content=content, name=name, tool_call_id=call_id)]
        }

    return approval_node


def _record(
    record: RecordFn | None, payload: dict, decision: dict, outcome: str
) -> None:
    if record is None:
        return
    try:
        record(payload, decision, outcome)
    except Exception:  # noqa: BLE001 - auditing must not break the turn
        logger.warning("could not record HITL decision", exc_info=True)
