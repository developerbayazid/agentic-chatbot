"""Per-process CLI session state shared by handlers and the input layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from rich.console import Console

from agentic_chatbot.cli.registry import Completion
from agentic_chatbot.container import ChatbotContainer

AskFn = Callable[[str, Sequence[Completion]], str]


def _unavailable_ask(prompt: str, completions: Sequence[Completion] = ()) -> str:
    raise RuntimeError("interactive prompt is not available in this context")


@dataclass
class ChatSession:
    """Mutable state for one interactive run.

    ``ask`` is injected by the input layer so command handlers can request an
    argument without knowing anything about prompt_toolkit.
    """

    container: ChatbotContainer
    console: Console
    current_thread_id: str
    ask: AskFn = field(default=_unavailable_ask)
    running: bool = True

    @property
    def thread_service(self):
        return self.container.thread_service

    @property
    def chat_service(self):
        return self.container.chat_service

    @property
    def settings(self):
        return self.container.settings

    def process(self, message: str) -> None:
        from agentic_chatbot.cli.chat import process_message

        process_message(self.console, self.chat_service, self.current_thread_id, message)

    def stop(self) -> None:
        self.running = False
