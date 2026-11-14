"""Rich rendering for the BAYAZID AI terminal interface.

Design goals: compact, left-aligned, minimal borders, one accent colour. Every
colour and typographic role comes from ``theme.py``; this module only decides
layout. No business logic lives here.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Sequence

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from agentic_chatbot.cli import background, theme
from agentic_chatbot.cli.glyphs import g
from agentic_chatbot.models import Thread

if TYPE_CHECKING:
    from agentic_chatbot.cli.registry import Command

APP_NAME = "BAYAZID AI"
APP_SUBTITLE = "Personal AI Assistant"
APP_TAGLINE = "Your intelligent workspace."

PALETTE = theme.PALETTE

# Backwards-compatible aliases used by command handlers.
BRAND = PALETTE.primary
ACCENT = PALETTE.primary
MUTED = PALETTE.muted
SUCCESS = PALETTE.success
WARNING = PALETTE.warning
DANGER = PALETTE.error


@dataclass(frozen=True)
class StatusSnapshot:
    """Safe-to-display runtime facts. Never carries secrets."""

    model: str
    database_path: str
    database_ok: bool
    graph_ok: bool
    tracing_enabled: bool
    thread_id: str
    thread_count: int
    tool_count: int = 0
    working_dir: str = ""


def make_console() -> Console:
    """Console with the brand theme registered so markup can use role names."""
    return Console(highlight=False, theme=theme.RICH_THEME)


# --- primitives --------------------------------------------------------------


def blank(console: Console, count: int = 1) -> None:
    for _ in range(count):
        console.print()


def _short(value: str, width: int) -> str:
    return value if len(value) <= width else value[: width - 1] + "\u2026"


def _facts(console: Console, rows: Sequence[tuple[str, str]], width: int = 0) -> None:
    """Print aligned label/value rows without trailing padding.

    A Rich grid pads every cell to its column width, which leaves invisible
    trailing whitespace and makes copied output messy. Labels are fixed-width
    strings, so aligning them by hand is both simpler and cleaner. Values that
    do not fit move to their own line rather than being silently truncated.
    """
    label_width = max((len(label) for label, _ in rows), default=0)
    gutter = " " * theme.GUTTER
    available = (width or console.width) - label_width - len(gutter) - 2

    for label, value in rows:
        if len(value) > available:
            console.print(Text(gutter + label, style=PALETTE.subtle))
            console.print(Text(gutter + value, style=PALETTE.body))
            continue

        line = Text(gutter)
        line.append(f"{label:<{label_width}}  ", style=PALETTE.subtle)
        line.append(value, style=PALETTE.body)
        console.print(line)


# --- welcome -----------------------------------------------------------------


def _stack(lines: Sequence[Text]) -> Text:
    """Join banner rows into one Text so a Panel preserves the row breaks."""
    combined = Text()
    for index, line in enumerate(lines):
        if index:
            combined.append("\n")
        combined.append_text(line)
    return combined


def _hero(console: Console, subtitle: str) -> None:
    """Emerald-grid hero: the brand lockup stamped over a neural lattice."""
    panel_width = min(console.width, 120)
    inner = max(panel_width - 4, 8)

    overlays = [
        Text(APP_NAME, style=PALETTE.title),
        Text(""),
        Text(subtitle, style=PALETTE.subtle),
    ]
    body = _stack(background.banner(inner, 7, overlays, seed=5))

    console.print(
        Panel(
            body,
            box=box.ROUNDED,
            border_style=PALETTE.primary_dim,
            padding=(0, 1),
            width=panel_width,
        )
    )


def _status_bullets(console: Console, status: StatusSnapshot) -> None:
    rows = [
        ("MODEL", status.model),
        (
            "STORAGE",
            f"SQLite {g('dot')} connected"
            if status.database_ok
            else f"SQLite {g('dot')} unreachable",
        ),
        ("GRAPH", "ready" if status.graph_ok else "unavailable"),
        ("TRACING", "on" if status.tracing_enabled else "off"),
        ("TOOLS", str(status.tool_count)),
        ("SESSION", _short(status.thread_id, 8)),
    ]
    columns = 2 if console.width >= 72 else 1
    label_width = max(len(label) for label, _ in rows)

    cells: list[Text] = []
    for label, value in rows:
        cell = Text()
        cell.append(f"{g('active')} ", style=PALETTE.command)
        cell.append(f"{label:<{label_width}}  ", style=PALETTE.subtle)
        cell.append(value, style=PALETTE.body)
        cells.append(cell)

    column_width = max(cell.cell_len for cell in cells) + 3
    for index in range(0, len(cells), columns):
        row = Text(" " * theme.GUTTER)
        group = cells[index : index + columns]
        for position, cell in enumerate(group):
            row.append_text(cell)
            if position < len(group) - 1:
                row.append(" " * (column_width - cell.cell_len))
        console.print(row)


def show_welcome(
    console: Console,
    status: StatusSnapshot = None,
    shortcuts: Sequence[tuple[str, str]] = (),
    version: str = "",
) -> None:
    """Startup hero: emerald-grid identity, live status, and quick-start hints."""
    blank(console)

    _hero(console, APP_SUBTITLE)

    meta = Text(" " * theme.GUTTER)
    meta.append(APP_TAGLINE, style=PALETTE.subtle)
    if version:
        meta.append(f"   {g('dot')}   ", style=PALETTE.very_subtle)
        meta.append(f"v{version}", style=PALETTE.very_subtle)
    console.print(meta)
    blank(console)

    if status is not None:
        _status_bullets(console, status)
        blank(console)

    if shortcuts:
        hints = Text(" " * theme.GUTTER)
        for index, (command, description) in enumerate(shortcuts):
            if index:
                hints.append(f"  {g('dot')}  ", style=PALETTE.very_subtle)
            hints.append(command, style=PALETTE.command)
            hints.append(f" {description}", style=PALETTE.subtle)
        console.print(hints)
        blank(console)

    footer = Text(" " * theme.GUTTER)
    footer.append("/help", style=PALETTE.command)
    footer.append(" for commands", style=PALETTE.subtle)
    footer.append(f"  {g('dot')}  ", style=PALETTE.very_subtle)
    footer.append("/exit", style=PALETTE.command)
    footer.append(" to quit", style=PALETTE.subtle)
    console.print(footer)
    blank(console)


def show_status_banner(
    console: Console,
    status: StatusSnapshot,
    show_database: bool = True,
) -> None:
    """Detailed status block used by ``/status``."""
    blank(console)
    console.print(Text(" " * theme.GUTTER + "STATUS", style=PALETTE.label))
    blank(console)

    facts: list[tuple[str, str]] = [("MODEL", status.model)]
    if show_database:
        facts.append(("DATABASE", status.database_path))
        facts.append(
            ("STORAGE", "connected" if status.database_ok else "unreachable")
        )
    facts.extend(
        [
            ("GRAPH", "ready" if status.graph_ok else "unavailable"),
            ("TRACING", "on" if status.tracing_enabled else "off"),
            ("TOOLS", str(status.tool_count)),
            ("THREADS", str(status.thread_count)),
            ("SESSION", status.thread_id),
        ]
    )

    _facts(console, facts)
    blank(console)


# --- messages ----------------------------------------------------------------


def user_message(console: Console, content: str) -> None:
    blank(console)
    console.print(Text("YOU", style=PALETTE.user))
    console.print(Text(content, style=PALETTE.body))


def assistant_header(console: Console) -> None:
    blank(console)
    console.print(Text(APP_NAME, style=PALETTE.label))


def stream_token(console: Console, token: str) -> None:
    console.print(token, end="", markup=False, highlight=False)


def markdown_block(content: str) -> Markdown:
    """Render completed assistant prose with Markdown and syntax highlighting."""
    return Markdown(content, code_theme="monokai", hyperlinks=False)


def assistant_done(console: Console) -> None:
    console.print()


# --- tool feedback -----------------------------------------------------------


def tool_call(console: Console, name: str | None, args: str) -> None:
    """Announce a tool run; the outcome line follows when it returns."""
    line = Text("  ")
    line.append(f"{g('active')} ", style=PALETTE.command)
    line.append(f"Executing tool: {name or 'tool'}", style=PALETTE.strong)
    line.append(f"  {g('active')} running", style=PALETTE.very_subtle)
    console.print(line)


def tool_result(
    console: Console,
    name: str | None,
    content: str,
    elapsed: float | None = None,
) -> None:
    failed = _looks_like_failure(content)
    style = PALETTE.danger if failed else PALETTE.ok

    line = Text("    ")
    line.append(f"{g('fail') if failed else g('done')} ", style=style)
    line.append("Failed" if failed else "Completed", style=style)
    if elapsed is not None:
        line.append(f"  {g('dot')} {elapsed:.1f}s", style=PALETTE.very_subtle)
    console.print(line)


def _looks_like_failure(content: str) -> bool:
    head = content.strip().lower()
    return head.startswith("error") or head.startswith("failed")


# --- human-in-the-loop -------------------------------------------------------


def approval_panel(console: Console, payload: dict) -> None:
    """Render one proposed sensitive action and the available decisions."""
    body = Text()
    body.append("Action: ", style=PALETTE.subtle)
    body.append(str(payload.get("title") or payload.get("tool") or "Sensitive action"), style=PALETTE.strong)

    rows = payload.get("details") or []
    if not rows:
        rows = [
            [str(key).replace("_", " ").title(), value]
            for key, value in (payload.get("arguments") or {}).items()
        ]

    if rows:
        body.append("\n")

    for label, value in rows:
        body.append("\n")
        body.append(f"{label}: ", style=PALETTE.subtle)
        body.append(str(value), style=PALETTE.body)

    body.append("\n\n")
    body.append("Requested By: ", style=PALETTE.subtle)
    body.append(str(payload.get("requested_by") or "AI Agent"), style=PALETTE.body)
    body.append("\n")
    body.append("Reason: ", style=PALETTE.subtle)
    body.append(str(payload.get("reason") or "User requested this operation"), style=PALETTE.body)

    warnings = payload.get("warnings") or []
    for message in warnings:
        body.append("\n")
        body.append(f"! {message}", style=PALETTE.warn)

    body.append("\n\n")
    body.append("[A] Approve", style=PALETTE.ok)
    body.append("    ")
    body.append("[E] Edit Arguments", style=PALETTE.warn)
    body.append("    ")
    body.append("[R] Reject", style=PALETTE.danger)

    console.print()
    console.print(
        Panel(
            body,
            title="HUMAN APPROVAL REQUIRED",
            title_align="center",
            box=box.ROUNDED,
            border_style=PALETTE.warning,
            padding=(0, 2),
        )
    )


def approval_diff(console: Console, original: dict, edited: dict) -> None:
    """Show only the arguments the human changed, original -> proposed."""
    rows = []
    for key in sorted(set(original) | set(edited)):
        before = original.get(key)
        after = edited.get(key)
        if before != after:
            rows.append((str(key), f"{before!r} -> {after!r}"))

    if not rows:
        notice(console, "No argument values changed.")
        return

    console.print()
    console.print(Text("  Proposed argument changes", style=PALETTE.label))
    for label, value in rows:
        line = Text("    ")
        line.append(f"{label}: ", style=PALETTE.subtle)
        line.append(value, style=PALETTE.body)
        console.print(line)


def approval_fields(console: Console, fields: Sequence[str], values: dict) -> None:
    """Numbered field list used by the field-level editor."""
    console.print()
    console.print(Text("  Editable arguments", style=PALETTE.label))

    if not fields:
        notice(console, "No editable fields were supplied for this action.")
        return

    for index, field in enumerate(fields, start=1):
        line = Text("    ")
        line.append(f"{index}. ", style=PALETTE.very_subtle)
        line.append(f"{field} = ", style=PALETTE.subtle)
        line.append(_display_value(values.get(field, "<not set>")), style=PALETTE.body)
        console.print(line)


def _display_value(value) -> str:
    if value == "<not set>":
        return value
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False)
        return text if len(text) <= 60 else text[:59] + "\u2026"
    return str(value)


def show_approvals(
    console: Console,
    thread_id: str,
    live: dict | None = None,
    seeded: dict | None = None,
    operator: str = "",
) -> None:
    """Read-only view of live graph interrupts and seeded business approvals."""
    blank(console)
    console.print(Text(" " * theme.GUTTER + "PENDING APPROVALS", style=PALETTE.label))
    blank(console)

    facts = [("THREAD", thread_id)]
    if operator:
        facts.append(("REVIEWER", operator))
    _facts(console, facts)
    blank(console)

    console.print(Text("  LIVE GRAPH INTERRUPT", style=PALETTE.very_subtle))
    value = (live or {}).get("value") or {}

    if live and isinstance(value, dict):
        rows = [
            ("ACTION", value.get("title") or value.get("tool") or "approval"),
            (
                "OPERATION",
                value.get("operation_id") or live.get("interrupt_id") or "-",
            ),
        ]
        arguments = value.get("arguments") or {}
        if arguments:
            rows.append(
                ("ARGUMENTS", json.dumps(arguments, ensure_ascii=False, default=str))
            )
        _facts(console, rows)
    else:
        notice(console, "No live interrupts for this thread.")

    blank(console)

    approvals = (seeded or {}).get("approvals") or []
    console.print(
        Text(
            f"  SEEDED BUSINESS APPROVALS ({len(approvals)})",
            style=PALETTE.very_subtle,
        )
    )

    if not approvals:
        notice(console, "No seeded business approvals are pending.")

    for item in approvals:
        line = Text("    ")
        line.append(str(item.get("approval_id", "")), style=PALETTE.command)
        line.append("   ")
        line.append(str(item.get("action", "")), style=PALETTE.body)
        line.append("   ")
        line.append(str(item.get("resource_type", "")), style=PALETTE.subtle)
        line.append(" ")
        line.append(str(item.get("resource_id", "")), style=PALETTE.subtle)
        console.print(line)

    blank(console)
    console.print(
        Text(
            "  Read-only. A decision panel appears the next time this thread continues.",
            style=PALETTE.very_subtle,
        )
    )
    blank(console)


# --- notices -----------------------------------------------------------------


def notice(console: Console, message: str) -> None:
    console.print()
    console.print(Text(f"  {message}", style=PALETTE.subtle))


def success(console: Console, message: str) -> None:
    console.print()
    console.print(Text(f"  {g('done')} {message}", style=PALETTE.ok))


def warning(console: Console, message: str) -> None:
    console.print()
    console.print(Text(f"  ! {message}", style=PALETTE.warn))


def error(console: Console, message: str) -> None:
    console.print()
    first, *rest = message.splitlines() or [""]

    line = Text("  ")
    line.append(f"{g('fail')} ", style=PALETTE.danger)
    line.append(first, style=PALETTE.danger)
    console.print(line)

    for continuation in rest:
        console.print(Text(f"    {continuation}", style=PALETTE.subtle))


# --- commands ----------------------------------------------------------------


def show_help(
    console: Console,
    commands: Sequence["Command"],
    category_order: Iterable[str],
) -> None:
    """Grouped command reference. Plain tables, no panels."""
    blank(console)
    console.print(Text(" " * theme.GUTTER + "COMMANDS", style=PALETTE.label))

    for category in category_order:
        entries = [command for command in commands if command.category == category]
        if not entries:
            continue

        blank(console)
        console.print(Text(f"  {category.upper()}", style=PALETTE.very_subtle))

        name_width = max(len(command.name) for command in entries)
        for command in entries:
            row = Text("  ")
            row.append(f"{command.name:<{name_width}}", style=PALETTE.command)
            row.append("   ")
            row.append(command.description, style=PALETTE.subtle)
            console.print(row)

    blank(console)
    hint = Text("  ")
    hint.append("/help <command>", style=PALETTE.command)
    hint.append(" for usage and examples", style=PALETTE.subtle)
    hint.append(f"  {g('dot')}  ", style=PALETTE.very_subtle)
    hint.append("plain text goes to the assistant", style=PALETTE.subtle)
    console.print(hint)
    blank(console)


def show_command_help(console: Console, command: "Command") -> None:
    blank(console)
    console.print(
        Text.assemble(
            ("  ", ""),
            (command.name, PALETTE.title),
            (f"   {command.description}", PALETTE.subtle),
        )
    )
    blank(console)

    _facts(
        console,
        [
            ("USAGE", command.usage),
            ("ARGUMENTS", command.arguments),
            ("EXAMPLE", command.example),
            ("BEHAVIOUR", command.behavior),
        ],
    )
    blank(console)


def show_threads(console: Console, threads: Sequence[Thread], current_thread_id: str) -> None:
    """Conversation list: columns when there is room, a stack when there is not."""
    if not threads:
        notice(console, "No conversations yet. Use /new to start one.")
        return

    blank(console)
    console.print(Text(" " * theme.GUTTER + "YOUR CONVERSATIONS", style=PALETTE.label))

    if console.width < 72:
        _show_threads_stacked(console, threads, current_thread_id)
    else:
        _show_threads_table(console, threads, current_thread_id)

    blank(console)


def _show_threads_table(
    console: Console,
    threads: Sequence[Thread],
    current_thread_id: str,
) -> None:
    """Aligned columns with manual padding, so there is no trailing whitespace."""
    gutter = " " * theme.GUTTER
    id_width = 8
    status_width = 6
    # Cap the title column so the table stays compact on very wide terminals
    # instead of stretching a short title across the whole screen.
    title_budget = max(min(console.width - id_width - status_width - 10, 44), 12)

    header = Text(gutter)
    header.append(f"{'ID':<{id_width}}  {'TITLE':<{title_budget}}  ", style=PALETTE.very_subtle)
    header.append("STATUS", style=PALETTE.very_subtle)
    console.print(header)

    blank(console)

    for thread in threads:
        active = thread.thread_id == current_thread_id
        title = _short(thread.title or "Untitled", title_budget)

        row = Text(gutter)
        row.append(f"{_short(thread.thread_id, id_width):<{id_width}}  ", style=PALETTE.subtle)
        row.append(f"{title:<{title_budget}}  ", style=PALETTE.body)
        row.append(
            "active" if active else "saved",
            style=PALETTE.label if active else PALETTE.very_subtle,
        )
        console.print(row)

    blank(console)
    console.print(
        Text(
            "  /delete accepts the full thread ID; Tab completes it.",
            style=PALETTE.very_subtle,
        )
    )


def _show_threads_stacked(
    console: Console,
    threads: Sequence[Thread],
    current_thread_id: str,
) -> None:
    blank(console)
    for thread in threads:
        active = thread.thread_id == current_thread_id
        title = Text(" " * theme.GUTTER)
        title.append(
            thread.title or "Untitled",
            style=PALETTE.strong if active else PALETTE.body,
        )
        if active:
            title.append(f"   {g('active')} active", style=PALETTE.label)
        console.print(title)
        console.print(
            Text(f"    {_short(thread.thread_id, 8)}", style=PALETTE.very_subtle)
        )


def show_history(console: Console, messages: Sequence) -> None:
    if not messages:
        notice(console, "No conversation history in this thread yet.")
        return

    blank(console)
    console.print(
        Text(" " * theme.GUTTER + "CONVERSATION HISTORY", style=PALETTE.label)
    )

    for message in messages:
        if message.type == "human":
            blank(console)
            console.print(Text(" " * theme.GUTTER + "YOU", style=PALETTE.user))
            console.print(Text(f"  {message.content}", style=PALETTE.body))
        elif message.type == "ai":
            blank(console)
            console.print(Text(" " * theme.GUTTER + APP_NAME, style=PALETTE.label))
            if message.content:
                console.print(markdown_block(str(message.content)))

    blank(console)


def document(console: Console, title: str, body: str) -> None:
    """Simple titled block used by ``/version``."""
    blank(console)
    console.print(Text(" " * theme.GUTTER + title.upper(), style=PALETTE.label))
    blank(console)
    console.print(Text("  " + body.replace("\n", "\n  "), style=PALETTE.body))
    blank(console)


def section(console: Console, title: str) -> None:
    blank(console)
    console.print(Text(" " * theme.GUTTER + title.upper(), style=PALETTE.label))


def database_ok(connection: sqlite3.Connection) -> bool:
    try:
        connection.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False
