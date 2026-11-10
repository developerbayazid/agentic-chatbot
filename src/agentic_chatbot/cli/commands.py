"""The application's command table.

This is the single source of truth for execution, autocomplete, help output, and
error suggestions. Add a command here and every surface picks it up.
"""

from __future__ import annotations

import platform
from importlib import metadata

from rich.console import Console
from rich.text import Text

from agentic_chatbot.cli import console as ui
from agentic_chatbot.cli.registry import (
    CATEGORY_CONVERSATION,
    CATEGORY_GENERAL,
    Command,
    Completion,
    normalize,
    resolve,
    similar_commands,
    split_input,
)
from agentic_chatbot.cli.session import ChatSession

PACKAGE_NAME = "agentic-chatbot"

CATEGORIES: tuple[str, ...] = (CATEGORY_GENERAL, CATEGORY_CONVERSATION)


def get_version() -> str:
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "0.0.0"


def _clear(session: ChatSession, argument: str) -> None:
    session.console.clear()


def _version(session: ChatSession, argument: str) -> None:
    ui.document(
        session.console,
        "Version",
        f"{ui.APP_NAME} {get_version()}\n"
        f"package   {PACKAGE_NAME}\n"
        f"python    {platform.python_version()}\n"
        f"platform  {platform.system()} {platform.release()}",
    )


def _status(session: ChatSession, argument: str) -> None:
    from agentic_chatbot.cli.chat import build_status

    ui.show_status_banner(session.console, build_status(session))


def _help(session: ChatSession, argument: str) -> None:
    if not argument:
        ui.show_help(session.console, COMMANDS, CATEGORIES)
        return

    command = resolve(COMMANDS, argument)

    if command is None:
        suggestions = similar_commands(COMMANDS, argument)
        if suggestions:
            names = ", ".join(item.name for item in suggestions)
            ui.warning(
                session.console,
                f"Unknown command: {normalize(argument)}. Did you mean: {names}?",
            )
        else:
            ui.warning(session.console, f"Unknown command: {normalize(argument)}")
        return

    ui.show_command_help(session.console, command)


def _exit(session: ChatSession, argument: str) -> None:
    session.console.print()
    session.console.print(
        Text("  Goodbye. Your conversations are saved.", style=ui.MUTED)
    )
    session.stop()


def _new(session: ChatSession, argument: str) -> None:
    thread = session.thread_service.create_thread()
    session.current_thread_id = thread.thread_id
    ui.success(session.console, f"New conversation created: {thread.thread_id}")


def _threads(session: ChatSession, argument: str) -> None:
    ui.show_threads(
        session.console,
        session.thread_service.list_threads(),
        session.current_thread_id,
    )


def _thread_ids(session: ChatSession, prefix: str) -> list[Completion]:
    prefix = prefix.strip()
    return [
        Completion(thread.thread_id, thread.title)
        for thread in session.thread_service.list_threads()
        if thread.thread_id.startswith(prefix)
    ]


def _known_thread(session: ChatSession, argument: str) -> str | None:
    """Validate a thread ID argument, or prompt for one."""
    thread_id = argument.strip() or session.ask(
        "Thread ID: ", _thread_ids(session, "")
    ).strip()

    if not thread_id:
        ui.warning(session.console, "No thread ID given. Use /threads to list them.")
        return None

    if not session.thread_service.thread_exists(thread_id):
        ui.error(session.console, f"Thread not found: {thread_id}")
        return None

    return thread_id


def _switch(session: ChatSession, argument: str) -> None:
    thread_id = _known_thread(session, argument)
    if thread_id is None:
        return

    session.current_thread_id = thread_id
    thread = session.thread_service.get_thread(thread_id)
    ui.success(session.console, f"Switched to {thread.title if thread else thread_id}")


def _history(session: ChatSession, argument: str) -> None:
    ui.show_history(
        session.console,
        session.chat_service.get_messages(session.current_thread_id),
    )


def _rename(session: ChatSession, argument: str) -> None:
    title = (argument or session.ask("New conversation title: ")).strip()

    if not title:
        ui.warning(session.console, "Title cannot be empty. Nothing changed.")
        return

    session.thread_service.rename_thread(session.current_thread_id, title)
    ui.success(session.console, f'Conversation renamed to "{title[:100]}"')


def _delete(session: ChatSession, argument: str) -> None:
    if not argument:
        ui.show_threads(
            session.console,
            session.thread_service.list_threads(),
            session.current_thread_id,
        )

    thread_id = _known_thread(session, argument)
    if thread_id is None:
        return

    answer = session.ask(f"Delete {thread_id} and its messages? (y/n): ")
    if answer.strip().lower() not in {"y", "yes"}:
        ui.notice(session.console, "Deletion cancelled.")
        return

    if not session.thread_service.delete_thread(thread_id):
        ui.error(session.console, f"Could not delete {thread_id}.")
        return

    if thread_id == session.current_thread_id:
        session.current_thread_id = session.thread_service.create_thread().thread_id
        ui.success(
            session.console,
            "Thread deleted. A new conversation is now active.",
        )
    else:
        ui.success(session.console, "Thread deleted.")


COMMANDS: list[Command] = [
    Command(
        name="/help",
        description="Show available commands, or details for one command",
        category=CATEGORY_GENERAL,
        usage="/help [command]",
        example="/help switch",
        behavior="Lists every command by category, or explains one command in detail.",
        arguments="Optional command name, with or without the leading slash.",
        handler=_help,
    ),
    Command(
        name="/clear",
        description="Clear the terminal screen",
        category=CATEGORY_GENERAL,
        usage="/clear",
        example="/clear",
        behavior="Clears the visible terminal only. Conversations and messages are kept.",
        arguments="None.",
        handler=_clear,
    ),
    Command(
        name="/status",
        description="Show model, database, graph, and tracing status",
        category=CATEGORY_GENERAL,
        usage="/status",
        example="/status",
        behavior="Prints runtime health information. Secrets are never shown.",
        arguments="None.",
        handler=_status,
    ),
    Command(
        name="/version",
        description="Show the application version",
        category=CATEGORY_GENERAL,
        usage="/version",
        example="/version",
        behavior="Reads the version from installed package metadata.",
        arguments="None.",
        handler=_version,
    ),
    Command(
        name="/exit",
        description="Exit the chatbot",
        category=CATEGORY_GENERAL,
        usage="/exit",
        example="/exit",
        behavior="Ends the session and closes the database connection.",
        arguments="None.",
        handler=_exit,
    ),
    Command(
        name="/new",
        description="Create a new conversation",
        category=CATEGORY_CONVERSATION,
        usage="/new",
        example="/new",
        behavior="Creates an empty thread and makes it active.",
        arguments="None.",
        handler=_new,
    ),
    Command(
        name="/threads",
        description="List all conversations",
        category=CATEGORY_CONVERSATION,
        usage="/threads",
        example="/threads",
        behavior="Shows titles, thread IDs, and last update times, marking the active one.",
        arguments="None.",
        handler=_threads,
    ),
    Command(
        name="/switch",
        description="Switch to another conversation",
        category=CATEGORY_CONVERSATION,
        usage="/switch [thread_id]",
        example="/switch 3f2c1b9a-7d4e-4c1a-9f2b-0a1b2c3d4e5f",
        behavior="Makes an existing thread active. Prompts with tab completion if no ID is given.",
        arguments="Thread ID. Tab-completes existing conversations.",
        handler=_switch,
        arg_completer=_thread_ids,
    ),
    Command(
        name="/history",
        description="Show the current conversation history",
        category=CATEGORY_CONVERSATION,
        usage="/history",
        example="/history",
        behavior="Renders the messages stored for the active thread.",
        arguments="None.",
        handler=_history,
    ),
    Command(
        name="/rename",
        description="Rename the current conversation",
        category=CATEGORY_CONVERSATION,
        usage="/rename [title]",
        example="/rename Q3 planning",
        behavior="Updates the active thread's title, truncated to 100 characters.",
        arguments="New title. Prompts if omitted.",
        handler=_rename,
    ),
    Command(
        name="/delete",
        description="Delete a conversation and its messages",
        category=CATEGORY_CONVERSATION,
        usage="/delete [thread_id]",
        example="/delete 3f2c1b9a-7d4e-4c1a-9f2b-0a1b2c3d4e5f",
        behavior="Confirms first, then deletes checkpoints and metadata. Deleting the active thread creates a replacement.",
        arguments="Thread ID. Tab-completes existing conversations.",
        handler=_delete,
        arg_completer=_thread_ids,
    ),
]


def dispatch(session: ChatSession, text: str) -> bool:
    """Execute a slash command.

    Returns ``True`` when the input was a command (handled or reported as
    unknown), ``False`` when it should be sent to the assistant.
    """
    name, argument = split_input(text)

    if not name.startswith("/"):
        return False

    command = resolve(COMMANDS, name)

    if command is None:
        _report_unknown(session.console, name)
        return True

    command.handler(session, argument)
    return True


def _report_unknown(console: Console, name: str) -> None:
    suggestions = similar_commands(COMMANDS, name)

    console.print()
    body = Text()
    body.append("  Unknown command: ", style=ui.PALETTE.warn)
    body.append(normalize(name), style=ui.PALETTE.strong)
    console.print(body)

    if suggestions:
        console.print(Text("  Did you mean?", style=ui.PALETTE.subtle))
        for command in suggestions:
            row = Text("    ")
            row.append(command.name, style=ui.PALETTE.command)
            row.append(f"   {command.description}", style=ui.PALETTE.subtle)
            console.print(row)
    else:
        hint = Text("  Type ")
        hint.append("/help", style=ui.PALETTE.command)
        hint.append(" to see every command.", style=ui.PALETTE.subtle)
        console.print(hint)

    console.print()
