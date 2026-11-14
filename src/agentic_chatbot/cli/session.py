"""Per-process CLI session state shared by handlers and the input layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from rich.console import Console

from agentic_chatbot.cli.registry import Completion
from agentic_chatbot.container import ChatbotContainer
from agentic_chatbot.models import Thread

AskFn = Callable[[str, Sequence[Completion]], str]
PickFn = Callable[["ChatSession", Sequence[Thread]], "Thread | None"]


def _unavailable_ask(prompt: str, completions: Sequence[Completion] = ()) -> str:
    raise RuntimeError("interactive prompt is not available in this context")


def _fallback_pick(session: "ChatSession", threads: Sequence[Thread]) -> Thread | None:
    """Non-interactive default: render the static list and make no selection."""
    from agentic_chatbot.cli import console as ui

    ui.show_threads(session.console, threads, session.current_thread_id)
    return None


@dataclass
class ChatSession:
    """Mutable state for one interactive run.

    ``ask`` and ``pick`` are injected by the input/presentation layer so command
    handlers can request an argument or choose a conversation without knowing
    anything about prompt_toolkit.
    """

    container: ChatbotContainer
    console: Console
    current_thread_id: str
    ask: AskFn = field(default=_unavailable_ask)
    approval_ask: AskFn | None = None
    pick: PickFn = field(default=_fallback_pick)
    running: bool = True

    @property
    def thread_service(self):
        return self.container.thread_service

    @property
    def chat_service(self):
        return self.container.chat_service

    @property
    def document_service(self):
        return self.container.document_service

    @property
    def inventory_service(self):
        return self.container.inventory_service

    @property
    def settings(self):
        return self.container.settings

    def process(self, message: str) -> None:
        from agentic_chatbot.cli.chat import process_message

        process_message(
            self.console,
            self.chat_service,
            self.current_thread_id,
            message,
            ask=self.approval_ask or self.ask,
        )

    def stop(self) -> None:
        self.running = False
