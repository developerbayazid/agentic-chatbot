"""Assistant turn rendering and runtime status assembly."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from agentic_chatbot.cli import approval
from agentic_chatbot.cli import console as ui
from agentic_chatbot.services.chat_service import ChatService

if TYPE_CHECKING:
    from agentic_chatbot.cli.console import StatusSnapshot
    from agentic_chatbot.cli.session import ChatSession

logger = logging.getLogger(__name__)

_LOOKAHEAD_CHARS = 80

_MARKDOWN_START = re.compile(
    r"^\s*(```|~~~|#{1,6}\s|>\s|\|.*\||[-*+]\s|\d+\.\s|---)"
)

STREAM = "stream"
MARKDOWN = "markdown"


def looks_like_markdown(text: str) -> bool:
    """True when a response begins a Markdown block worth rendering.

    Only the first line is inspected: prose that merely *contains* markdown
    keeps streaming token by token, which preserves the live typing feel.
    """
    first_line = text.splitlines()[0] if text.strip() else ""
    return bool(_MARKDOWN_START.match(first_line))


class _Response:
    """Decides per response whether to stream raw or render Markdown."""

    def __init__(self, console: Console):
        self._console = console
        self._buffer = ""
        self._mode: str | None = None
        self._open_line = False

    def push(self, token: str) -> None:
        if self._mode == STREAM:
            ui.stream_token(self._console, token)
            self._open_line = True
            return

        self._buffer += token

        if self._mode is None and (
            "\n" in self._buffer or len(self._buffer) >= _LOOKAHEAD_CHARS
        ):
            self._mode = MARKDOWN if looks_like_markdown(self._buffer) else STREAM
            if self._mode == STREAM:
                ui.stream_token(self._console, self._buffer)
                self._buffer = ""
                self._open_line = True

    def flush(self) -> None:
        """Emit anything still buffered, then reset for the next message."""
        remainder, self._buffer = self._buffer, ""

        if self._mode == MARKDOWN:
            if remainder.strip():
                self._console.print(ui.markdown_block(remainder))
                self._open_line = False
        elif remainder:
            ui.stream_token(self._console, remainder)
            self._open_line = True

        self._mode = None

    def close_line(self) -> None:
        """Terminate a streamed line so following blocks start on their own row."""
        if self._open_line:
            self._console.print()
            self._open_line = False

    @property
    def wrote_output(self) -> bool:
        return self._mode is not None or bool(self._buffer)


def process_message(
    console: Console,
    chat_service: ChatService,
    thread_id: str,
    user_message: str,
    ask=None,
) -> None:
    """Stream one assistant turn, rendering events as they arrive.

    When the graph interrupts for human approval, the panel is shown, the
    decision is collected, and the same turn resumes. A rejection returns a tool
    result to the model; nothing is executed.
    """
    if _has_pending_approval(chat_service, thread_id):
        # The previous turn ended without a decision. Resolve it before adding a
        # new human message; otherwise the graph would call the model with an
        # unanswered tool call and the provider rejects the message history.
        resume_pending(console, chat_service, thread_id, ask)

        if _has_pending_approval(chat_service, thread_id):
            ui.warning(
                console,
                "Your new message was not sent. Decide the pending action first.",
            )
            return

    ui.user_message(console, user_message)
    ui.assistant_header(console)

    response = _Response(console)

    try:
        title = _drive_turn(
            console,
            chat_service,
            thread_id,
            chat_service.stream_turn(thread_id, user_message),
            response,
            ask,
        )
    except KeyboardInterrupt:
        console.print()
        raise
    except Exception as error:  # noqa: BLE001 - surfaced to the user, logged for details
        logger.debug("assistant turn failed", exc_info=True)
        response.flush()
        ui.assistant_done(console)
        ui.error(console, f"Could not complete this response.\n{error}")
        return

    response.flush()
    ui.assistant_done(console)
    if title:
        ui.notice(console, f"Conversation title: {title}")


def resume_pending(
    console: Console,
    chat_service: ChatService,
    thread_id: str,
    ask=None,
) -> bool:
    """Resolve an approval interrupt persisted by an earlier process.

    Returns ``True`` when a pending approval existed, whether or not the human
    decided to act on it. Nothing is executed without a decision.
    """
    pending = chat_service.get_pending_interrupt(thread_id)
    payload = (pending or {}).get("value")

    if not isinstance(payload, dict):
        return False

    ui.assistant_header(console)
    ui.notice(console, "A previous action is still awaiting human approval.")

    response = _Response(console)

    try:
        decision = approval.prompt_decision(console, ask, payload)

        if decision is None:
            ui.warning(
                console,
                "The action remains pending and was not executed. "
                "It can still be approved later in this conversation.",
            )
            ui.notice(
                console,
                "Returning to chat. Use /approvals to inspect pending actions.",
            )
            return True

        ui.notice(console, "Approval recorded. Continuing…")
        title = _drive_turn(
            console,
            chat_service,
            thread_id,
            chat_service.resume_turn(thread_id, decision),
            response,
            ask,
        )
    except KeyboardInterrupt:
        console.print()
        raise
    except Exception as error:  # noqa: BLE001 - keep the CLI alive
        logger.debug("resuming approval failed", exc_info=True)
        response.flush()
        ui.assistant_done(console)
        ui.error(console, f"Could not resume the approval.\n{error}")
        return True

    response.flush()
    ui.assistant_done(console)
    if title:
        ui.notice(console, f"Conversation title: {title}")

    return True


def _has_pending_approval(chat_service: ChatService, thread_id: str) -> bool:
    getter = getattr(chat_service, "get_pending_interrupt", None)
    if getter is None:
        return False

    try:
        return getter(thread_id) is not None
    except Exception:  # noqa: BLE001 - a missing thread has no pending approval
        return False


def _drive_turn(
    console: Console,
    chat_service: ChatService,
    thread_id: str,
    events,
    response: _Response,
    ask,
) -> str | None:
    """Consume one or more streams, resolving any approval interrupts."""
    tool_started: dict[str, float] = {}
    title: str | None = None

    while True:
        interrupt_payload: dict | None = None

        for event in events:
            if event.type == "token":
                response.push(event.content)
            elif event.type == "tool_call":
                response.flush()
                response.close_line()
                tool_started[event.name or "tool"] = time.monotonic()
                ui.tool_call(console, event.name, event.content)
            elif event.type == "tool_result":
                started = tool_started.pop(event.name or "tool", None)
                elapsed = time.monotonic() - started if started is not None else None
                ui.tool_result(console, event.name, event.content, elapsed)
            elif event.type == "interrupt":
                interrupt_payload = event.payload or {}
            elif event.type == "done":
                if event.title:
                    title = event.title

        if interrupt_payload is None:
            return title

        response.flush()
        response.close_line()

        decision = approval.prompt_decision(console, ask, interrupt_payload)

        if decision is None:
            ui.warning(
                console,
                "Action not executed. It remains pending for a later approval.",
            )
            ui.notice(
                console,
                "Returning to chat. Use /approvals to inspect pending actions.",
            )
            return title

        ui.notice(console, "Approval recorded. Continuing…")
        events = chat_service.resume_turn(thread_id, decision)


def build_status(session: "ChatSession") -> "StatusSnapshot":
    """Collect display-safe runtime facts."""
    container = session.container
    database_ok = ui.database_ok(container.connection)

    try:
        thread_count = len(container.thread_service.list_threads())
    except Exception:  # noqa: BLE001 - status must never crash the CLI
        logger.debug("thread count unavailable", exc_info=True)
        thread_count = 0

    return ui.StatusSnapshot(
        model=session.settings.llm_model,
        database_path=session.settings.database_path,
        database_ok=database_ok,
        graph_ok=hasattr(container, "chatbot"),
        tracing_enabled=bool(session.settings.langsmith_tracing),
        thread_id=session.current_thread_id,
        thread_count=thread_count,
        tool_count=len(getattr(container, "tools", ())),
        working_dir=str(Path.cwd()),
    )
