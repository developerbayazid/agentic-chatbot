"""Terminal interaction for human approval of sensitive tool calls.

Editing is field-by-field rather than raw JSON: the reviewer picks a numbered
argument, enters a value, and the CLI coerces it to the tool's declared type.
Every prompt terminates its line so the approval screen cannot leave the
terminal looking stuck.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Sequence

from rich.console import Console

from agentic_chatbot.cli import console as ui
from agentic_chatbot.cli.registry import Completion

AskFn = Callable[[str, Sequence[Completion]], str]

_APPROVE = {"a", "approve", "y", "yes"}
_REJECT = {"r", "reject", "n", "no"}
_EDIT = {"e", "edit"}
_CANCEL = {"c", "cancel", "q", "quit"}


def prompt_decision(
    console: Console, ask: AskFn | None, payload: dict
) -> dict | None:
    """Show the panel and collect an approve/edit/reject decision.

    Returns ``None`` when no decision was made, which means the action must stay
    unexecuted and pending. The decision carries the approval token so the graph
    can reject a decision that no longer matches the proposal.
    """
    ui.approval_panel(console, payload)

    if ask is None:
        ui.warning(
            console,
            "No interactive prompt is available here. The action was not executed.",
        )
        return None

    token = payload.get("approval_token")
    original = dict(payload.get("arguments") or {})
    editable = list(payload.get("editable_fields") or original)
    field_types = payload.get("field_types") or {}

    for _ in range(8):
        choice = _ask(console, ask, "Decision [A]pprove / [E]dit / [R]eject: ")

        if choice is None:
            return None

        normalized = choice.lower().lstrip("/")

        if not normalized:
            ui.notice(console, "Approval left pending. Returning to chat.")
            return None

        if normalized in _APPROVE:
            comment = _ask(console, ask, "Comment (optional): ") or ""
            return {
                "action": "approve",
                "approval_token": token,
                "comment": comment,
            }

        if normalized in _REJECT:
            reason = _ask(console, ask, "Rejection reason (optional): ") or ""
            return {
                "action": "reject",
                "approval_token": token,
                "comment": reason,
            }

        if normalized in _EDIT:
            edited = _edit_fields(
                console, ask, original, editable, field_types
            )

            if edited is None:
                continue

            ui.approval_diff(console, original, edited)
            confirm = (
                _ask(console, ask, "Execute with these arguments? (y/n): ") or ""
            ).lower()

            if confirm in {"y", "yes"}:
                return {
                    "action": "edit",
                    "arguments": edited,
                    "approval_token": token,
                    "comment": "Arguments edited by the human reviewer.",
                }
            continue

        ui.warning(console, "Please choose A (approve), E (edit), or R (reject).")

    ui.warning(console, "No valid decision was entered. The action was not executed.")
    return None


def _ask(console: Console, ask: AskFn, question: str) -> str | None:
    """Ask one question and always terminate the prompt line.

    ``None`` means the prompt could not be read (no console or interrupted);
    an empty string means the reviewer answered with a blank line.
    """
    try:
        answer = ask(question)
    except Exception:  # noqa: BLE001 - no prompt means no approval
        return None

    console.print()
    return answer.strip()


def _edit_fields(
    console: Console,
    ask: AskFn,
    original: dict,
    editable: list[str],
    field_types: dict,
) -> dict | None:
    """Edit arguments one field at a time. ``None`` cancels the edit."""
    edited = dict(original)

    while True:
        ui.approval_fields(console, editable, edited)

        selection = _ask(
            console,
            ask,
            "Field to edit (number/name, 'c' to cancel, blank to finish): ",
        )

        if selection is None:
            return None

        if selection.lower() in _CANCEL:
            ui.notice(console, "Edit cancelled. No changes were applied.")
            return None

        if not selection:
            if edited == original:
                ui.notice(console, "No arguments changed.")
                return None
            return edited

        field = _resolve_field(selection, editable)

        if field is None:
            ui.warning(
                console,
                f"Unknown field: {selection}. Use a number or an exact field name.",
            )
            continue

        current = edited.get(field, "<not set>")
        raw = _ask(console, ask, f"{field} [{current}]: ")

        if raw is None:
            return None

        if raw == "":
            continue

        try:
            value = _coerce_value(raw, edited.get(field), field_types.get(field, ""))
        except (ValueError, json.JSONDecodeError) as error:
            ui.error(console, f"Invalid value for {field}: {error}")
            continue

        edited[field] = value
        ui.notice(console, f"{field} will be set to {value!r}.")


def _resolve_field(selection: str, fields: list[str]) -> str | None:
    if selection.isdigit():
        index = int(selection) - 1
        if 0 <= index < len(fields):
            return fields[index]
        return None

    if selection in fields:
        return selection

    lowered = selection.lower()
    for field in fields:
        if field.lower() == lowered:
            return field
    return None


def _coerce_value(raw: str, current: Any, schema_type: str) -> Any:
    """Convert the reviewer's text to the tool's argument type."""
    kind = (schema_type or "").lower()

    if not kind:
        if isinstance(current, bool):
            kind = "boolean"
        elif isinstance(current, int):
            kind = "integer"
        elif isinstance(current, float):
            kind = "number"
        elif isinstance(current, list):
            kind = "array"
        elif isinstance(current, dict):
            kind = "object"
        elif isinstance(current, str):
            kind = "string"
        else:
            kind = "scalar"

    if kind == "boolean":
        return _as_bool(raw)

    if kind == "integer":
        return int(raw)

    if kind == "number":
        value = float(raw)
        return int(value) if value.is_integer() else value

    if kind in {"array", "object"}:
        return json.loads(raw)

    if kind == "string":
        return raw

    return _parse_scalar(raw)


def _as_bool(raw: str) -> bool:
    lowered = raw.strip().lower()
    if lowered in {"true", "t", "yes", "y", "1"}:
        return True
    if lowered in {"false", "f", "no", "n", "0"}:
        return False
    raise ValueError("expected true/false, yes/no, or 1/0")


def _parse_scalar(raw: str) -> Any:
    lowered = raw.strip().lower()

    if lowered in {"null", "none"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"

    try:
        return int(raw)
    except ValueError:
        pass

    try:
        return float(raw)
    except ValueError:
        return raw
