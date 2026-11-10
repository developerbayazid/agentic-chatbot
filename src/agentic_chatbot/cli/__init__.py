"""Terminal presentation layer.

Layout:

- ``registry`` — command record, lookup, fuzzy matching, suggestion helpers (pure).
- ``commands`` — the single command table plus handlers and dispatch.
- ``console``  — Rich rendering (banner, tables, messages, errors).
- ``session``  — per-run state shared by handlers and the input layer.
- ``chat``     — assistant turn streaming and runtime status.
- ``input``    — prompt_toolkit completion and the interactive prompt.
- ``app``      — the loop and ``main()``.

Only presentation lives here. Conversation logic stays in the services and the
graph, so a future HTTP layer can reuse them unchanged.
"""

from agentic_chatbot.cli.app import main, run_session
from agentic_chatbot.cli.commands import COMMANDS, CATEGORIES, dispatch
from agentic_chatbot.cli.session import ChatSession

__all__ = [
    "CATEGORIES",
    "COMMANDS",
    "ChatSession",
    "dispatch",
    "main",
    "run_session",
]
