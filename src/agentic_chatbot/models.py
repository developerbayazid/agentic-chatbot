"""Domain models shared across services and the CLI."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Thread:
    thread_id: str
    title: str
    created_at: str | None
    updated_at: str | None


@dataclass(frozen=True)
class TurnEvent:
    """A single event emitted while processing one conversation turn."""

    type: Literal["token", "tool_call", "tool_result", "done"]
    content: str = ""
    title: str | None = None
    name: str | None = None
