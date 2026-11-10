"""Completion, glyph fallback, session loop, and input routing."""

import io
import sys

import pytest
from prompt_toolkit.document import Document
from rich.console import Console

from agentic_chatbot.cli import glyphs
from agentic_chatbot.cli import input as input_module
from agentic_chatbot.cli.app import run_session
from agentic_chatbot.cli.commands import COMMANDS
from agentic_chatbot.cli.input import CommandCompleter
from agentic_chatbot.cli.session import ChatSession
from agentic_chatbot.models import Thread


class FakeThreadService:
    def __init__(self, threads):
        self._threads = threads

    def list_threads(self):
        return list(self._threads)


class FakeSession:
    def __init__(self):
        self.thread_service = FakeThreadService(
            [
                Thread("abc-123", "Alpha chat", "x", "y"),
                Thread("abd-456", "Beta chat", "x", "y"),
            ]
        )


def completions(text):
    completer = CommandCompleter(FakeSession(), COMMANDS)
    return list(completer.get_completions(Document(text), None))


def test_slash_lists_every_command():
    entries = completions("/")

    assert {item.text for item in entries} == {
        command.name for command in COMMANDS
    }


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("/th", "/threads"),
        ("/swi", "/switch"),
        ("/ren", "/rename"),
        ("/hel", "/help"),
    ],
)
def test_partial_command_completes_to_full_name(typed, expected):
    assert [item.text for item in completions(typed)] == [expected]


def test_completion_replaces_the_typed_prefix():
    entry = completions("/th")[0]

    assert entry.start_position == -3
    assert entry.text == "/threads"


def test_completion_carries_description_metadata():
    entry = completions("/threads")[0]

    assert entry.display_meta_text == "List all conversations"


def test_normal_chat_text_produces_no_completions():
    assert completions("hello there") == []


def test_argument_completion_uses_real_thread_ids():
    entries = completions("/switch ab")

    assert [item.text for item in entries] == ["abc-123", "abd-456"]


def test_argument_completion_filters_by_prefix():
    entries = completions("/switch abd")

    assert [item.text for item in entries] == ["abd-456"]


def test_argument_completion_replaces_argument_only():
    entry = completions("/switch abc")[0]

    assert entry.start_position == -3


def test_delete_command_also_completes_thread_ids():
    entries = completions("/delete abc")

    assert [item.text for item in entries] == ["abc-123"]


def test_commands_without_argument_completer_return_nothing():
    assert completions("/history ") == []


def test_unknown_command_with_argument_returns_nothing():
    assert completions("/bogus arg") == []


@pytest.mark.parametrize(
    ("encoding", "expected_symbol"),
    [("utf-8", "●"), ("cp1252", "*"), ("ascii", "*"), ("latin-1", "*")],
)
def test_glyph_set_adapts_to_stdout_encoding(monkeypatch, encoding, expected_symbol):
    class FakeStdout:
        def __init__(self, stream_encoding):
            self.encoding = stream_encoding

    monkeypatch.setattr(sys, "stdout", FakeStdout(encoding))
    glyphs.unicode_ok.cache_clear()

    try:
        assert glyphs.g("active") == expected_symbol
    finally:
        glyphs.unicode_ok.cache_clear()


def test_glyph_lookup_of_unknown_name_returns_empty():
    assert glyphs.g("nope") == ""


class ScriptedPrompt:
    """Minimal stand-in for a prompt_toolkit session."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def prompt(self, *args, **kwargs):
        self.prompts.append(kwargs.get("message"))
        if not self.responses:
            raise EOFError
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def test_run_session_exits_on_exit_command(container):
    console = Console(width=100, record=True)
    prompt = ScriptedPrompt(["/exit"])

    run_session(container, console, prompt)

    text = console.export_text()
    assert "BAYAZID AI" in text
    assert "Goodbye" in text


def test_run_session_handles_eof(container):
    console = Console(width=100, record=True)

    run_session(container, console, ScriptedPrompt([]))

    assert "BAYAZID AI" in console.export_text()


def test_run_session_survives_keyboard_interrupt_then_exits(container):
    console = Console(width=100, record=True)
    prompt = ScriptedPrompt([KeyboardInterrupt(), "/exit"])

    run_session(container, console, prompt)

    assert "Goodbye" in console.export_text()


def test_run_session_routes_plain_text_to_the_assistant(container, monkeypatch):
    console = Console(width=100, record=True)
    prompt = ScriptedPrompt(["hello assistant", "/exit"])
    captured = []

    monkeypatch.setattr(
        ChatSession,
        "process",
        lambda self, message: captured.append(message),
    )

    run_session(container, console, prompt)

    assert captured == ["hello assistant"]


def test_run_session_does_not_send_commands_to_the_assistant(container, monkeypatch):
    console = Console(width=100, record=True)
    prompt = ScriptedPrompt(["/threads", "/bogus", "/exit"])
    captured = []

    monkeypatch.setattr(
        ChatSession,
        "process",
        lambda self, message: captured.append(message),
    )

    run_session(container, console, prompt)

    assert captured == []


def test_run_session_skips_blank_input(container, monkeypatch):
    console = Console(width=100, record=True)
    prompt = ScriptedPrompt(["   ", "/exit"])
    captured = []

    monkeypatch.setattr(
        ChatSession,
        "process",
        lambda self, message: captured.append(message),
    )

    run_session(container, console, prompt)

    assert captured == []


def test_run_session_reports_unexpected_errors_without_dying(container, monkeypatch):
    console = Console(width=100, record=True)
    prompt = ScriptedPrompt(["boom", "/exit"])

    def explode(self, message):
        raise RuntimeError("exploded")

    monkeypatch.setattr(ChatSession, "process", explode)

    run_session(container, console, prompt)

    text = console.export_text()
    assert "Unexpected error: exploded" in text
    assert "Goodbye" in text


def test_run_session_resumes_most_recent_thread(container):
    existing = container.thread_service.create_thread("Existing chat")
    console = Console(width=100, record=True)

    run_session(container, console, ScriptedPrompt(["/exit"]))

    assert "Resuming: Existing chat" in console.export_text()
    assert container.thread_service.get_thread(existing.thread_id) is not None


def test_run_session_creates_thread_when_none_exist(container):
    console = Console(width=100, record=True)

    run_session(container, console, ScriptedPrompt(["/exit"]))

    assert "New conversation created" in console.export_text()
    assert len(container.thread_service.list_threads()) == 1


def test_ask_returns_empty_string_on_interrupt():
    prompt = ScriptedPrompt([KeyboardInterrupt()])
    ask = input_module.make_ask(prompt)

    assert ask("Title? ") == ""


def test_ask_strips_whitespace():
    prompt = ScriptedPrompt(["  spaced  "])
    ask = input_module.make_ask(prompt)

    assert ask("Title? ") == "spaced"


def test_ask_offers_argument_completions():
    from agentic_chatbot.cli.registry import Completion

    prompt = ScriptedPrompt(["abc-123"])
    ask = input_module.make_ask(prompt)

    assert ask("Thread? ", [Completion("abc-123", "Alpha chat")]) == "abc-123"
    assert prompt.prompts


def test_command_completions_text_groups_commands():
    grouped_names = input_module.command_completions_text(COMMANDS)

    assert "/help" in grouped_names["General"]
    assert "/threads" in grouped_names["Conversation"]


# --- Hermes-style status line ------------------------------------------------


@pytest.fixture
def session(container):
    from rich.console import Console

    from agentic_chatbot.cli.session import ChatSession

    thread = container.thread_service.create_thread("Toolbar chat")
    return ChatSession(
        container=container,
        console=Console(width=100),
        current_thread_id=thread.thread_id,
    )


def test_status_toolbar_shows_model_and_short_thread(session):
    fragments = input_module._status_toolbar(session)
    joined = "".join(text for _, text in fragments)

    assert session.settings.llm_model in joined
    assert session.current_thread_id[:8] in joined
    assert "/help" in joined
    assert "ctrl+d exit" in joined


def test_status_toolbar_never_leaks_secrets(session):
    joined = "".join(text for _, text in input_module._status_toolbar(session))

    assert session.settings.openai_api_key not in joined
    assert session.settings.database_path not in joined


def test_status_toolbar_uses_the_dot_separator(session):
    joined = "".join(text for _, text in input_module._status_toolbar(session))

    assert " · " in joined


def test_bottom_toolbar_is_callable(session):
    toolbar = input_module._bottom_toolbar(session)

    assert callable(toolbar)
    assert any("gpt" in text for _, text in toolbar())


@pytest.mark.parametrize("name", ["active", "prompt", "done", "fail", "dot"])
def test_interface_glyphs_exist(name):
    assert glyphs.g(name)


def test_unicode_glyphs_are_the_expected_symbols(monkeypatch):
    monkeypatch.setattr("agentic_chatbot.cli.glyphs.unicode_ok", lambda: True)

    assert glyphs.g("prompt") == "❯"
    assert glyphs.g("done") == "✓"
    assert glyphs.g("fail") == "✗"


def test_ascii_glyphs_are_safe_fallbacks(monkeypatch):
    monkeypatch.setattr("agentic_chatbot.cli.glyphs.unicode_ok", lambda: False)

    assert glyphs.g("prompt") == ">"
    assert glyphs.g("done") == "+"
    assert glyphs.g("fail") == "x"
