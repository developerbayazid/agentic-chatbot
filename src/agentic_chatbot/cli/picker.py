"""Interactive session picker for ``/threads``.

A prompt_toolkit application: a search box over a live table of conversations
with keyboard navigation. Selecting a row switches the active thread. The whole
thing degrades to the static list (:func:`ui.show_threads`) when a real terminal
is not available, so piped input, CI, and tests keep working.

Layout::

    › Type to search sessions…
    ─────────────────────────────────────────────
    #    Modified   Git Branch   Messages   Summary
    1.   18h ago    -            270        Terminal UI Redesign  ●
    ...
    ↑/↓ move · Enter open · Esc cancel
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Sequence

from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    ConditionalContainer,
    Float,
    FloatContainer,
    HSplit,
    Layout,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style

from agentic_chatbot.cli import console as ui
from agentic_chatbot.cli import theme

if TYPE_CHECKING:
    from rich.console import Console

    from agentic_chatbot.cli.session import ChatSession
    from agentic_chatbot.models import Thread

logger = logging.getLogger(__name__)

PLACEHOLDER = "Type to search sessions\u2026"
HINT = "\u2191/\u2193 move  \u00b7  Enter open  \u00b7  Esc cancel"


@dataclass(frozen=True)
class SessionRow:
    """One line in the picker table."""

    position: int
    thread_id: str
    title: str
    modified: str
    branch: str
    messages: int
    active: bool = False


# --- data --------------------------------------------------------------------


def relative_time(value: str | None, now: datetime | None = None) -> str:
    """Render a SQLite UTC timestamp as a short relative age (``18h ago``)."""
    if not value:
        return "-"

    moment = _parse_timestamp(value)
    if moment is None:
        return "-"

    reference = now or datetime.now(timezone.utc)
    seconds = max((reference - moment).total_seconds(), 0)

    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    if seconds < 86400 * 30:
        return f"{int(seconds // 86400)}d ago"
    if seconds < 86400 * 365:
        return f"{int(seconds // (86400 * 30))}mo ago"
    return f"{int(seconds // (86400 * 365))}y ago"


def _parse_timestamp(value: str) -> datetime | None:
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _message_count(session: "ChatSession", thread_id: str) -> int:
    try:
        return len(session.chat_service.get_messages(thread_id))
    except Exception:  # noqa: BLE001 - a picker must never crash on one thread
        logger.debug("message count unavailable", exc_info=True)
        return 0


def build_rows(session: "ChatSession", threads: Sequence["Thread"]) -> list[SessionRow]:
    """Turn threads into table rows with recency, message count, and active flag."""
    rows: list[SessionRow] = []
    for position, thread in enumerate(threads, start=1):
        rows.append(
            SessionRow(
                position=position,
                thread_id=thread.thread_id,
                title=thread.title or "Untitled",
                modified=relative_time(thread.updated_at),
                branch="-",
                messages=_message_count(session, thread.thread_id),
                active=thread.thread_id == session.current_thread_id,
            )
        )
    return rows


def filter_rows(rows: Sequence[SessionRow], query: str) -> list[SessionRow]:
    """Case-insensitive substring match on the summary; empty query keeps all."""
    needle = query.strip().lower()
    if not needle:
        return list(rows)
    return [row for row in rows if needle in row.title.lower()]


# --- interactive picker ------------------------------------------------------


class _PickerState:
    """Mutable selection/search state shared by the layout and key bindings."""

    def __init__(self, rows: Sequence[SessionRow], width_getter):
        self.rows = list(rows)
        self.filtered = list(rows)
        self.selected = 0
        self.search = Buffer(on_text_changed=self._on_change)
        self._width = width_getter

    def _on_change(self, _buffer: Buffer) -> None:
        self.filtered = filter_rows(self.rows, self.search.text)
        self.selected = 0

    def move(self, delta: int) -> None:
        if self.filtered:
            self.selected = (self.selected + delta) % len(self.filtered)

    def current(self) -> SessionRow | None:
        return self.filtered[self.selected] if self.filtered else None

    def visible(self) -> list[tuple[int, SessionRow]]:
        """Return ``(global_index, row)`` pairs for the visible window."""
        width = self._width()
        capacity = max(width, 4)
        if len(self.filtered) <= capacity:
            return list(enumerate(self.filtered))

        start = min(
            max(self.selected - capacity // 2, 0),
            len(self.filtered) - capacity,
        )
        return list(enumerate(self.filtered))[start : start + capacity]


def _fit(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: max(width - 1, 0)] + "\u2026"


def _header_line(width: int) -> str:
    return f"  {'#':<3} {'Modified':<10} {'Git Branch':<11} {'Messages':>7}  Summary"


def _row_line(row: SessionRow, width: int, selected: bool) -> str:
    marker = "\u203a" if selected else " "
    summary_width = max(width - 40, 8)
    summary = _fit(row.title, summary_width)
    active = "\u25cf" if row.active else " "
    return (
        f"{marker} {f'{row.position}.':<3} {row.modified:<10} "
        f"{row.branch:<11} {row.messages:>7}  {summary}  {active}"
    )


_PICKER_STYLE = Style.from_dict(
    {
        "": f"bg:{theme.BACKGROUND} {theme.TEXT}",
        "prompt": f"bold {theme.BRAND_HEX}",
        "placeholder": theme.FAINT,
        "rule": theme.RULE,
        "header": theme.FAINT,
        "row": theme.TEXT,
        "row.active": theme.MUTED,
        "selected": f"bg:{theme.BRAND_HEX} {theme.TEXT_STRONG} bold",
        "muted": theme.FAINT,
        "hint": theme.FAINT,
    }
)


def _terminal_width() -> int:
    try:
        import shutil

        return max(shutil.get_terminal_size((80, 24)).columns - 1, 24)
    except OSError:
        return 79


def build_application(
    rows: Sequence[SessionRow],
    *,
    input=None,
    output=None,
) -> tuple[Application, _PickerState]:
    """Construct the picker Application and its state (exposed for tests)."""
    state = _PickerState(rows, width_getter=_terminal_width)

    def table_fragments():
        width = _terminal_width()
        fragments: list[tuple[str, str]] = [
            ("class:header", _header_line(width) + "\n"),
        ]
        visible = state.visible()
        if not visible:
            fragments.append(("class:muted", "  No matching sessions\n"))
        for index, row in visible:
            selected = index == state.selected
            style = "class:selected" if selected else (
                "class:row.active" if row.active else "class:row"
            )
            fragments.append((style, _row_line(row, width, selected) + "\n"))
        return fragments

    search_window = Window(
        BufferControl(buffer=state.search),
        height=1,
        get_line_prefix=lambda *_: [("class:prompt", "\u203a ")],
    )
    rule = Window(height=1, char="\u2500", style="class:rule")
    table = Window(
        FormattedTextControl(table_fragments),
        dont_extend_height=True,
        height=Dimension(min=1),
    )
    hint = Window(
        FormattedTextControl([("class:hint", "  " + HINT)]),
        height=1,
    )
    body = HSplit([search_window, rule, table, hint])

    placeholder = Float(
        ConditionalContainer(
            Window(FormattedTextControl([("class:placeholder", PLACEHOLDER)])),
            filter=Condition(lambda: not state.search.text),
        ),
        top=0,
        left=2,
    )

    layout = Layout(FloatContainer(body, floats=[placeholder]), focused_element=search_window)
    bindings = _key_bindings(state)
    application = Application(
        layout=layout,
        key_bindings=bindings,
        style=_PICKER_STYLE,
        full_screen=True,
        input=input,
        output=output,
    )
    return application, state


def _key_bindings(state: _PickerState) -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("up")
    def _up(event) -> None:
        state.move(-1)

    @bindings.add("down")
    def _down(event) -> None:
        state.move(1)

    @bindings.add("enter")
    def _accept(event) -> None:
        event.app.exit(result=state.current())

    @bindings.add("escape")
    @bindings.add("c-c")
    @bindings.add("c-d")
    def _cancel(event) -> None:
        event.app.exit(result=None)

    return bindings


def _run_picker(
    rows: Sequence[SessionRow],
    *,
    input=None,
    output=None,
) -> SessionRow | None:
    application, _state = build_application(rows, input=input, output=output)
    return application.run()


def supports_interactive(prompt_session) -> bool:
    """True when the main prompt is a real terminal session (not a fallback)."""
    return isinstance(prompt_session, PromptSession)


def pick(session: "ChatSession", threads: Sequence["Thread"]) -> "Thread | None":
    """Run the interactive picker; return the chosen thread or ``None``."""
    rows = build_rows(session, threads)
    try:
        chosen = _run_picker(rows)
    except Exception:  # noqa: BLE001 - never let the picker break the session
        logger.debug("interactive picker failed", exc_info=True)
        ui.show_threads(session.console, threads, session.current_thread_id)
        return None

    if chosen is None:
        return None
    return session.thread_service.get_thread(chosen.thread_id)


__all__ = [
    "SessionRow",
    "build_application",
    "build_rows",
    "filter_rows",
    "pick",
    "relative_time",
    "supports_interactive",
]
