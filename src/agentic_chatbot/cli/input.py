"""Interactive input layer built on prompt_toolkit.

Provides command suggestions, tab completion, argument completion, and input
history while leaving normal chat text untouched.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Sequence

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion as PTCompletion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.console import Console

from agentic_chatbot.cli import theme
from agentic_chatbot.cli.glyphs import g, unicode_ok
from agentic_chatbot.cli.registry import (
    Command,
    Completion,
    grouped,
    resolve,
    split_input,
    suggest,
)
from agentic_chatbot.cli.session import ChatSession

logger = logging.getLogger(__name__)

PROMPT_TEXT = [("class:prompt", f"\n{g('prompt')} ")]

# Brand accent on the prompt and the selected completion; the menu stays on a
# neutral surface so descriptions remain easy to scan.
STYLE = Style.from_dict(
    {
        "": theme.TEXT_STRONG,
        "prompt": f"bold {theme.BRAND_HEX}",
        "frame": theme.PALETTE.rule,
        "toolbar": f"bg:{theme.PALETTE.rule} {theme.PALETTE.muted}",
        "toolbar.keyword": f"bg:{theme.PALETTE.rule} {theme.BRAND_HEX} bold",
        "toolbar.model": f"bg:{theme.PALETTE.rule} {theme.PALETTE.text_strong} bold",
        "completion-menu.completion": f"bg:{theme.PALETTE.rule} {theme.PALETTE.body}",
        "completion-menu.completion.current": (
            f"bg:{theme.BRAND_HEX} {theme.TEXT_STRONG} bold"
        ),
        "completion-menu.meta.completion": (
            f"bg:{theme.PALETTE.rule} {theme.PALETTE.muted}"
        ),
        "completion-menu.meta.completion.current": (
            f"bg:{theme.BRAND_HEX} {theme.TEXT_STRONG}"
        ),
    }
)


def _frame_chars() -> tuple[str, str]:
    """Box characters that degrade to ASCII when the terminal lacks Unicode."""
    if unicode_ok():
        return ("\u2500", "\u2502")
    return ("-", "|")


def framed_message():
    """A width-adaptive framed prompt: faint top rule, left rail, emerald prompt.

    Re-evaluated on every render, so the rule tracks terminal resizes. The frame
    is decorative only: completion, history, and key bindings are configured
    separately on the session and are unaffected.
    """
    rule_char, rail_char = _frame_chars()

    def render() -> list[tuple[str, str]]:
        try:
            width = shutil.get_terminal_size((80, 24)).columns
        except OSError:
            width = 80
        rule = rule_char * max(width - 1, 8)
        return [
            ("class:frame", "\n" + rule + "\n"),
            ("class:frame", f"{rail_char} "),
            ("class:prompt", f"{g('prompt')} "),
        ]

    return render


def _status_toolbar(session: ChatSession) -> list[tuple[str, str]]:
    """Slim status line under the composer."""
    model = session.settings.llm_model
    thread = session.current_thread_id
    short_thread = thread[:8] if thread else "-"
    directory = Path.cwd().name or str(Path.cwd())
    dot = g("dot")

    return [
        ("class:toolbar", " "),
        ("class:toolbar.model", model),
        ("class:toolbar", f"  {dot}  {short_thread}"),
        ("class:toolbar", f"  {dot}  {directory}"),
        ("class:toolbar", f"  {dot}  "),
        ("class:toolbar.keyword", "/help"),
        ("class:toolbar", f"  {dot}  enter send  {dot}  ctrl+d exit "),
    ]


def _bottom_toolbar(session: ChatSession):
    return lambda: _status_toolbar(session)


class CommandCompleter(Completer):
    """Command and argument completion driven by the command registry."""

    def __init__(self, session: ChatSession, commands: Sequence[Command]):
        self._session = session
        self._commands = list(commands)

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor

        if text.startswith("/") and " " in text:
            yield from self._argument_completions(text)
            return

        if not text.startswith("/"):
            return

        for command in suggest(self._commands, text):
            yield PTCompletion(
                command.name,
                start_position=-len(text),
                display=_display(command.name),
                display_meta=command.description,
            )

    def _argument_completions(self, text: str):
        name, argument = split_input(text)
        command = resolve(self._commands, name)

        if command is None or command.arg_completer is None:
            return

        for item in command.arg_completer(self._session, argument):
            yield PTCompletion(
                item.text,
                start_position=-len(argument),
                display=_display(item.text),
                display_meta=item.description,
            )


def _display(text: str) -> str:
    return text[:36] + "..." if len(text) > 39 else text


def _key_bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("c-d")
    def _exit(event) -> None:
        if event.current_buffer.text:
            event.current_buffer.delete()
            return
        event.current_buffer.validate_and_handle()

    return bindings


def build_prompt_session(session: ChatSession, commands: Sequence[Command]):
    """Build the interactive prompt, or ``None`` when no console is available.

    prompt_toolkit requires a real terminal. Piped input, CI, and some legacy
    Windows shells have no screen buffer, so callers fall back to ``input()``.
    """
    try:
        return PromptSession(
            completer=CommandCompleter(session, commands),
            history=InMemoryHistory(),
            complete_while_typing=True,
            key_bindings=_key_bindings(),
            style=STYLE,
            message=framed_message(),
            reserve_space_for_menu=6,
            enable_history_search=False,
            bottom_toolbar=_bottom_toolbar(session),
        )
    except Exception:  # noqa: BLE001 - any output backend failure means "no TTY"
        logger.debug("prompt_toolkit unavailable, falling back to plain input", exc_info=True)
        return None


class PlainPrompt:
    """Minimal prompt used when prompt_toolkit cannot attach to a terminal."""

    def prompt(self, message="", *args, **kwargs) -> str:
        if isinstance(message, str):
            text = message
        else:
            text = "".join(fragment[1] for fragment in message) if message else ""
        try:
            return input(text.strip() or "\n> ")
        except (EOFError, KeyboardInterrupt):
            raise


def read_input(prompt_session) -> str:
    """Read one line; ``EOFError``/``KeyboardInterrupt`` propagate to the caller."""
    return prompt_session.prompt()


def make_ask(prompt_session):
    """Build the ``session.ask`` callable used by command handlers."""

    def ask(question: str, completions: Sequence[Completion] = ()) -> str:
        try:
            if isinstance(prompt_session, PlainPrompt):
                return prompt_session.prompt(f"\n  {question}")

            return prompt_session.prompt(
                FormattedText([("class:prompt", f"\n  {question}")]),
                completer=_OneShotCompleter(list(completions)) if completions else None,
                complete_while_typing=False,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    return ask


def make_approval_ask(console: Console):
    """Line prompt for approval decisions, outside the framed composer.

    Reusing the main ``PromptSession`` for nested approval questions can leave
    the approval line on screen after the turn, so the main prompt looks stuck.
    A separate Rich prompt keeps the composer state untouched.
    """

    def ask(question: str, completions: Sequence[Completion] = ()) -> str:
        try:
            return console.input(f"  {question}", markup=False).strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    return ask


class _OneShotCompleter(Completer):
    def __init__(self, items: list[Completion]):
        self._items = items

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        for item in self._items:
            if item.text.startswith(text):
                yield PTCompletion(
                    item.text,
                    start_position=-len(text),
                    display=_display(item.text),
                    display_meta=item.description,
                )


def command_completions_text(commands: Sequence[Command]) -> dict[str, list[str]]:
    """Category -> command names, used by docs and tests."""
    return {
        category: [command.name for command in entries]
        for category, entries in grouped(list(commands))
    }
