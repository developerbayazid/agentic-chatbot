"""Command table, dispatch routing, and handler behaviour."""

import pytest
from rich.console import Console

from agentic_chatbot.cli import commands as command_module
from agentic_chatbot.cli import console as ui
from agentic_chatbot.cli.commands import CATEGORIES, COMMANDS, dispatch
from agentic_chatbot.cli.registry import normalize
from agentic_chatbot.cli.session import ChatSession


@pytest.fixture
def console():
    return Console(width=100, record=True)


@pytest.fixture
def session(container, console):
    thread = container.thread_service.create_thread("Test chat")
    return ChatSession(
        container=container,
        console=console,
        current_thread_id=thread.thread_id,
    )


def output(console):
    return console.export_text()


def test_every_command_is_unique_and_well_formed():
    names = [command.name for command in COMMANDS]

    assert len(names) == len(set(names))
    assert all(name.startswith("/") for name in names)
    assert all(command.description for command in COMMANDS)
    assert all(command.usage for command in COMMANDS)
    assert all(command.category in CATEGORIES for command in COMMANDS)


def test_documented_commands_are_registered():
    assert set(names_of_commands()) == {
        "/help",
        "/clear",
        "/status",
        "/version",
        "/exit",
        "/new",
        "/threads",
        "/switch",
        "/history",
        "/rename",
        "/delete",
    }


def names_of_commands():
    return [command.name for command in COMMANDS]


def test_plain_text_is_not_a_command(session):
    assert dispatch(session, "hello there") is False


@pytest.mark.parametrize("text", ["", "   "])
def test_blank_input_is_not_a_command(session, text):
    assert dispatch(session, text) is False


def test_unknown_command_is_handled_and_never_forwarded(session, console, monkeypatch):
    forwarded = []
    monkeypatch.setattr(session, "process", lambda message: forwarded.append(message))

    assert dispatch(session, "/threds") is True
    assert forwarded == []

    text = output(console)
    assert "Unknown command: /threds" in text
    assert "/threads" in text


def test_unknown_command_without_close_match_points_to_help(session, console):
    dispatch(session, "/zzzzzz")

    text = output(console)
    assert "Unknown command: /zzzzzz" in text
    assert "/help" in text


def test_help_lists_commands_by_category(session, console):
    dispatch(session, "/help")

    text = output(console)
    for category in CATEGORIES:
        assert category.upper() in text
    for command in COMMANDS:
        assert command.name in text


def test_help_for_single_command_shows_usage_and_example(session, console):
    dispatch(session, "/help switch")

    text = output(console)
    assert "/switch" in text
    assert "/switch [thread_id]" in text
    assert "Thread ID. Tab-completes existing conversations." in text


def test_help_accepts_names_without_slash(session, console):
    dispatch(session, "/help rename")

    assert "/rename [title]" in output(console)


def test_help_suggests_alternatives_for_unknown_topic(session, console):
    dispatch(session, "/help threds")

    text = output(console)
    assert "Unknown command: /threds" in text
    assert "/threads" in text


def test_new_command_creates_and_activates_thread(session, console):
    before = session.current_thread_id

    dispatch(session, "/new")

    assert session.current_thread_id != before
    assert "New conversation created" in output(console)
    assert session.thread_service.thread_exists(session.current_thread_id)


def test_threads_command_marks_active_thread(session, container, console):
    container.thread_service.create_thread("Another chat")

    dispatch(session, "/threads")

    text = output(console)
    assert "Test chat" in text
    assert "Another chat" in text
    assert "active" in text


def test_switch_to_known_thread(session, container, console):
    other = container.thread_service.create_thread("Other chat")

    dispatch(session, f"/switch {other.thread_id}")

    assert session.current_thread_id == other.thread_id
    assert "Switched to Other chat" in output(console)


def test_switch_rejects_unknown_thread(session, console):
    before = session.current_thread_id

    dispatch(session, "/switch missing-thread")

    assert session.current_thread_id == before
    assert "Thread not found: missing-thread" in output(console)


def test_switch_prompts_with_argument_completions(session, console, monkeypatch):
    other = session.thread_service.create_thread("Prompted chat")
    asked = {}

    def fake_ask(question, completions=()):
        asked["question"] = question
        asked["completions"] = [item.text for item in completions]
        return other.thread_id

    monkeypatch.setattr(session, "ask", fake_ask)

    dispatch(session, "/switch")

    assert session.current_thread_id == other.thread_id
    assert other.thread_id in asked["completions"]
    assert set(asked["completions"]) == {
        thread.thread_id for thread in session.thread_service.list_threads()
    }


def test_thread_argument_completer_returns_real_threads(session):
    switch = next(command for command in COMMANDS if command.name == "/switch")
    threads = session.thread_service.list_threads()

    completions = switch.arg_completer(session, threads[0].thread_id[:4])

    assert [item.text for item in completions] == [threads[0].thread_id]
    assert completions[0].description == threads[0].title


def test_rename_updates_current_thread(session, console):
    dispatch(session, "/rename Renamed chat")

    thread = session.thread_service.get_thread(session.current_thread_id)
    assert thread.title == "Renamed chat"
    assert "Renamed chat" in output(console)


def test_rename_prompts_when_title_is_missing(session, console, monkeypatch):
    monkeypatch.setattr(session, "ask", lambda question, completions=(): "From prompt")

    dispatch(session, "/rename")

    assert session.thread_service.get_thread(session.current_thread_id).title == "From prompt"


def test_rename_rejects_blank_title(session, console, monkeypatch):
    monkeypatch.setattr(session, "ask", lambda question, completions=(): "   ")
    before = session.thread_service.get_thread(session.current_thread_id).title

    dispatch(session, "/rename")

    after = session.thread_service.get_thread(session.current_thread_id).title
    assert after == before
    assert "Title cannot be empty" in output(console)


def test_delete_requires_confirmation(session, console, monkeypatch):
    thread_id = session.current_thread_id
    monkeypatch.setattr(session, "ask", lambda question, completions=(): "n")

    dispatch(session, f"/delete {thread_id}")

    assert session.thread_service.thread_exists(thread_id)
    assert "Deletion cancelled" in output(console)


def test_delete_active_thread_creates_replacement(session, console, monkeypatch):
    thread_id = session.current_thread_id
    monkeypatch.setattr(session, "ask", lambda question, completions=(): "y")

    dispatch(session, f"/delete {thread_id}")

    assert not session.thread_service.thread_exists(thread_id)
    assert session.current_thread_id != thread_id
    assert session.thread_service.thread_exists(session.current_thread_id)
    assert "new conversation is now active" in output(console).lower()


def test_delete_inactive_thread_keeps_current(session, container, console, monkeypatch):
    other = container.thread_service.create_thread("Doomed")
    monkeypatch.setattr(session, "ask", lambda question, completions=(): "y")

    dispatch(session, f"/delete {other.thread_id}")

    assert not container.thread_service.thread_exists(other.thread_id)
    assert session.current_thread_id != other.thread_id


def test_delete_unknown_thread_reports_error(session, console):
    dispatch(session, "/delete missing-thread")

    assert "Thread not found: missing-thread" in output(console)


def test_history_shows_messages(session, console, monkeypatch):
    from langchain_core.messages import AIMessage, HumanMessage

    monkeypatch.setattr(
        session.chat_service,
        "get_messages",
        lambda thread_id: [HumanMessage(content="hello"), AIMessage(content="hi there")],
    )

    dispatch(session, "/history")

    text = output(console)
    assert "hello" in text
    assert "hi there" in text


def test_history_reports_empty_conversation(session, console):
    dispatch(session, "/history")

    assert "No conversation history" in output(console)


def test_status_never_exposes_secrets(settings, container, console):
    from agentic_chatbot.cli.chat import build_status

    session = ChatSession(
        container=container,
        console=console,
        current_thread_id=container.thread_service.create_thread().thread_id,
    )

    status = build_status(session)

    assert status.model == settings.llm_model
    assert status.database_ok is True
    assert status.graph_ok is True
    assert settings.openai_api_key not in repr(status)
    assert settings.openai_api_key not in output(console)


def test_status_command_renders(full_session, console):
    dispatch(full_session, "/status")

    text = output(console)
    assert "STATUS" in text
    assert "MODEL" in text
    assert full_session.settings.llm_model in text
    assert "DATABASE" in text


def test_status_command_shows_database_path(full_session, console):
    dispatch(full_session, "/status")

    # Long paths move to their own line, so compare with whitespace collapsed.
    rendered = "".join(output(console).split())
    for border in "│┃|":
        rendered = rendered.replace(border, "")

    assert "".join(full_session.settings.database_path.split()) in rendered


def test_welcome_banner_hides_database_path(full_session, console):
    from agentic_chatbot.cli.chat import build_status

    ui.show_welcome(console, build_status(full_session))

    text = output(console)
    assert "MODEL" in text
    assert "GRAPH" in text
    assert "DATABASE" not in text
    assert full_session.settings.database_path not in text


def test_version_reads_package_metadata(full_session, console):
    dispatch(full_session, "/version")

    text = output(console)
    assert "BAYAZID AI" in text
    assert "0.1.0" in text


def test_clear_clears_the_screen(full_session, console):
    dispatch(full_session, "/clear")

    assert console.export_text() == ""


def test_exit_stops_the_session(full_session, console):
    assert full_session.running is True

    dispatch(full_session, "/exit")

    assert full_session.running is False
    assert "Goodbye" in output(console)


def test_dispatch_normalizes_case_and_extra_spaces(full_session, console):
    assert dispatch(full_session, "  /HELP  ") is True
    assert "GENERAL" in output(console)


def test_tool_and_success_messages_render(session, console):
    ui.tool_call(console, "calculator", '{"expression": "2+2"}')
    ui.tool_result(console, "calculator", "4")
    ui.success(console, "done")

    text = output(console)
    assert "calculator" in text
    assert "done" in text


def test_unknown_command_uses_normalize_for_display(session, console):
    dispatch(session, "  /BOGUS  ")

    assert f"Unknown command: {normalize('/BOGUS')}" in output(console)


@pytest.fixture
def full_session(container, console):
    thread = container.thread_service.create_thread("Status chat")
    session = ChatSession(
        container=container,
        console=console,
        current_thread_id=thread.thread_id,
    )
    return session


def test_commands_module_exposes_categories():
    assert command_module.CATEGORIES == CATEGORIES
