"""Agentic AI chatbot package."""

from typing import Any


def main() -> Any:
    from agentic_chatbot.cli import main as _main

    return _main()


__all__ = ["main"]
