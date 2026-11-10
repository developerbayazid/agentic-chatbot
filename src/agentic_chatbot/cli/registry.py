"""Central command registry primitives.

This module is deliberately presentation-free and handler-free: it defines the
``Command`` record, category ordering, and the lookup/fuzzy/suggestion helpers
used by execution, autocomplete, help, and error recovery.

The actual command table lives in ``commands.py`` so this module stays free of
imports that would create a cycle (``commands`` -> ``registry``).
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from typing import Any, Callable

CATEGORY_GENERAL = "General"
CATEGORY_CONVERSATION = "Conversation"

CATEGORY_ORDER: tuple[str, ...] = (CATEGORY_GENERAL, CATEGORY_CONVERSATION)


@dataclass(frozen=True)
class Completion:
    """A single argument completion candidate."""

    text: str
    description: str = ""


Handler = Callable[[Any, str], None]
ArgCompleter = Callable[[Any, str], list[Completion]]


@dataclass(frozen=True)
class Command:
    """Everything the CLI needs to know about one slash command."""

    name: str
    description: str
    category: str
    usage: str
    example: str
    behavior: str
    arguments: str
    handler: Handler
    arg_completer: ArgCompleter | None = None


def normalize(name: str) -> str:
    """Return a canonical ``/name`` form for lookups."""
    cleaned = name.strip().lower()
    if not cleaned:
        return cleaned
    return cleaned if cleaned.startswith("/") else f"/{cleaned}"


def command_names(commands: list[Command]) -> list[str]:
    return [command.name for command in commands]


def resolve(commands: list[Command], name: str) -> Command | None:
    """Find a command by name, accepting ``help`` and ``/help``."""
    target = normalize(name)
    for command in commands:
        if command.name == target:
            return command
    return None


def _category_rank(category: str) -> tuple[int, str]:
    try:
        return (CATEGORY_ORDER.index(category), "")
    except ValueError:
        return (len(CATEGORY_ORDER), category)


def grouped(commands: list[Command]) -> list[tuple[str, list[Command]]]:
    """Return ``(category, commands)`` pairs in display order."""
    buckets: dict[str, list[Command]] = {}
    for command in commands:
        buckets.setdefault(command.category, []).append(command)

    ordered = sorted(buckets, key=_category_rank)
    return [
        (category, sorted(buckets[category], key=lambda item: item.name))
        for category in ordered
    ]


def suggest(commands: list[Command], prefix: str) -> list[Command]:
    """Return prefix matches, or fuzzy matches when nothing starts with ``prefix``."""
    prefix = prefix.strip().lower()

    if not prefix.startswith("/"):
        return []

    matches = [command for command in commands if command.name.startswith(prefix)]
    if matches:
        return sorted(matches, key=lambda item: (_category_rank(item.category), item.name))

    return similar_commands(commands, prefix)


def similar_commands(
    commands: list[Command],
    name: str,
    limit: int = 3,
) -> list[Command]:
    """Fuzzy-match an unknown command name against the registry."""
    target = normalize(name)
    if not target:
        return []

    candidates = get_close_matches(
        target,
        command_names(commands),
        n=limit,
        cutoff=0.6,
    )
    resolved = [resolve(commands, candidate) for candidate in candidates]
    return [command for command in resolved if command is not None]


def split_input(text: str) -> tuple[str, str]:
    """Split raw input into ``(command_part, argument)``.

    ``"/switch abc"`` -> ``("/switch", "abc")``; ``"/help"`` -> ``("/help", "")``.
    """
    stripped = text.strip()
    if not stripped:
        return ("", "")

    name, _, argument = stripped.partition(" ")
    return (name, argument.strip())
