import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agentic_chatbot.cli import (
    _run_interactive,
    process_message,
    show_help,
    show_history,
    show_threads,
)
from agentic_chatbot.models import Thread, TurnEvent


class FakeChatService:
    def __init__(self, events=None, error=None):
        self.events = events or []
        self.error = error

    def stream_turn(self, thread_id, user_message):
        if self.error is not None:
            raise self.error

        for event in self.events:
            yield event


def test_process_message_prints_tokens_and_title(capsys):
    service = FakeChatService(
        events=[
            TurnEvent(type="token", content="Hello"),
            TurnEvent(type="token", content=" world"),
            TurnEvent(type="done", title="Greeting"),
        ]
    )

    process_message(service, "thread-1", "hi")

    output = capsys.readouterr().out
    assert "Hello world" in output
    assert "Conversation title: Greeting" in output


def test_process_message_reports_stream_errors(capsys):
    service = FakeChatService(error=RuntimeError("boom"))

    process_message(service, "thread-1", "hi")

    output = capsys.readouterr().out
    assert "Error while generating response: boom" in output


def test_show_threads_marks_active_thread(capsys):
    threads = [
        Thread("thread-1", "First", "2024-01-01", "2024-01-01"),
        Thread("thread-2", "Second", "2024-01-02", "2024-01-02"),
    ]

    show_threads(threads, "thread-2")

    output = capsys.readouterr().out
    assert "1. First\n" in output
    assert "2. Second  <-- Active" in output


def test_show_threads_handles_empty_list(capsys):
    show_threads([], "thread-1")

    assert "No conversations found." in capsys.readouterr().out


def test_show_history_maps_roles_and_hides_system(capsys):
    class ThreadService:
        def thread_exists(self, thread_id):
            return True

    class ChatService:
        def get_messages(self, thread_id):
            return [
                SystemMessage(content="internal"),
                HumanMessage(content="hello"),
                AIMessage(content="hi there"),
            ]

    show_history(ThreadService(), ChatService(), "thread-1")

    output = capsys.readouterr().out
    assert "You: hello" in output
    assert "Assistant: hi there" in output
    assert "internal" not in output


def test_show_history_handles_missing_thread(capsys):
    class ThreadService:
        def thread_exists(self, thread_id):
            return False

    show_history(ThreadService(), FakeChatService(), "thread-1")

    assert "Thread not found." in capsys.readouterr().out


def test_show_history_handles_empty_history(capsys):
    class ThreadService:
        def thread_exists(self, thread_id):
            return True

    class ChatService:
        def get_messages(self, thread_id):
            return []

    show_history(ThreadService(), ChatService(), "thread-1")

    assert "No conversation history found." in capsys.readouterr().out


def test_show_help_lists_commands(capsys):
    show_help()

    output = capsys.readouterr().out
    for command in ("/new", "/threads", "/switch", "/history", "/rename", "/delete", "/exit"):
        assert command in output


def test_run_interactive_creates_and_renames_thread(container, monkeypatch):
    responses = iter(["/new", "/rename", "My Chat", "/exit"])
    monkeypatch.setattr("builtins.input", lambda *args: next(responses))

    _run_interactive(container)

    titles = [thread.title for thread in container.thread_service.list_threads()]
    assert "My Chat" in titles


def test_run_interactive_exits_cleanly(container, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *args: "/exit")

    _run_interactive(container)

    assert "Goodbye!" in capsys.readouterr().out
