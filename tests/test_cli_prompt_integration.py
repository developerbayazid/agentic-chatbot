"""Prompt integration test: Tab autocomplete through a real PromptSession.

Uses prompt_toolkit's pipe input and a dummy output so no terminal is needed.
The driver waits for the buffer to change rather than sleeping a fixed time, so
the test is not sensitive to machine speed.
"""

import threading
import time

import pytest
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.shortcuts import PromptSession
from rich.console import Console

from agentic_chatbot.cli.commands import COMMANDS
from agentic_chatbot.cli.input import CommandCompleter, PROMPT_TEXT, STYLE
from agentic_chatbot.cli.session import ChatSession

TIMEOUT = 5.0


@pytest.fixture
def session(container):
    thread = container.thread_service.create_thread("Completion chat")
    return ChatSession(
        container=container,
        console=Console(width=100),
        current_thread_id=thread.thread_id,
    )


def _wait_for_buffer(prompt, expected, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if prompt.default_buffer.text == expected:
            return True
        time.sleep(0.02)
    return False


def _run_prompt(session, pipe, typed, expected):
    prompt = PromptSession(
        completer=CommandCompleter(session, COMMANDS),
        history=InMemoryHistory(),
        complete_while_typing=True,
        style=STYLE,
        message=PROMPT_TEXT,
        input=pipe,
        output=DummyOutput(),
    )

    def feed():
        time.sleep(0.2)
        for character in typed:
            pipe.send_text(character)
            time.sleep(0.02)

        # Give the completion menu a chance to appear, then accept it.
        assert _wait_for_buffer(prompt, typed)
        time.sleep(0.15)
        pipe.send_text("\t")
        assert _wait_for_buffer(prompt, expected), prompt.default_buffer.text
        pipe.send_text("\r")

    thread = threading.Thread(target=feed, daemon=True)
    thread.start()
    result = prompt.prompt()
    thread.join(timeout=TIMEOUT)
    return result


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("/thr", "/threads"),
        ("/swi", "/switch"),
        ("/ren", "/rename"),
        ("/hel", "/help"),
    ],
)
def test_tab_completes_partial_commands(session, typed, expected):
    with create_pipe_input() as pipe:
        assert _run_prompt(session, pipe, typed, expected) == expected


def test_tab_completes_thread_id_argument(session, container):
    other = container.thread_service.create_thread("Another chat")
    prefix = other.thread_id[:6]

    with create_pipe_input() as pipe:
        result = _run_prompt(
            session,
            pipe,
            f"/switch {prefix}",
            f"/switch {other.thread_id}",
        )

    assert result == f"/switch {other.thread_id}"


def test_plain_text_is_not_altered_by_completion(session):
    with create_pipe_input() as pipe:
        result = _run_prompt(session, pipe, "hello assistant", "hello assistant")

    assert result == "hello assistant"
