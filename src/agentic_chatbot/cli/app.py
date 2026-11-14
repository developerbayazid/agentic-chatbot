"""Interactive session loop and application entry point."""

from __future__ import annotations

import logging
import sys

from rich.console import Console

from agentic_chatbot.cli import console as ui
from agentic_chatbot.cli import picker
from agentic_chatbot.cli.chat import build_status, resume_pending
from agentic_chatbot.cli.commands import COMMANDS, dispatch, get_version
from agentic_chatbot.cli.input import (
    PlainPrompt,
    build_prompt_session,
    make_approval_ask,
    make_ask,
    read_input,
)
from agentic_chatbot.cli.session import ChatSession
from agentic_chatbot.config import get_settings
from agentic_chatbot.container import ChatbotContainer, build_container

logger = logging.getLogger(__name__)


def _initial_thread_id(container: ChatbotContainer, console: Console) -> str:
    threads = container.thread_service.list_threads()

    if threads:
        ui.notice(console, f"Resuming: {threads[0].title}")
        return threads[0].thread_id

    thread = container.thread_service.create_thread()
    ui.notice(console, "New conversation created.")
    return thread.thread_id


def run_session(
    container: ChatbotContainer,
    console: Console | None = None,
    prompt_session=None,
) -> None:
    """Run the interactive loop until the user exits.

    ``prompt_session`` is injectable so tests can drive the loop without a TTY.
    """
    console = console or ui.make_console()

    session = ChatSession(
        container=container,
        console=console,
        current_thread_id=_initial_thread_id(container, console),
    )

    ui.show_welcome(
        console,
        build_status(session),
        shortcuts=(
            ("/help", "commands"),
            ("/threads", "conversations"),
            ("/new", "new conversation"),
        ),
        version=get_version(),
    )

    if prompt_session is None:
        prompt_session = build_prompt_session(session, COMMANDS) or PlainPrompt()

    session.ask = make_ask(prompt_session)
    session.approval_ask = make_approval_ask(console)
    if picker.supports_interactive(prompt_session):
        session.pick = picker.pick

    # A checkpoint may hold an approval interrupt from a previous process. Offer
    # it before the normal input loop so the same thread ID resumes correctly.
    try:
        resume_pending(
            console,
            container.chat_service,
            session.current_thread_id,
            session.approval_ask,
        )
    except KeyboardInterrupt:
        console.print()
    except Exception as error:  # noqa: BLE001 - startup must not crash the CLI
        logger.debug("pending approval check failed", exc_info=True)
        ui.error(console, f"Could not check pending approvals: {error}")

    while session.running:
        try:
            user_input = read_input(prompt_session)
        except EOFError:
            console.print()
            session.stop()
            break
        except KeyboardInterrupt:
            continue

        if not user_input.strip():
            continue

        try:
            if dispatch(session, user_input):
                continue
            session.process(user_input)
        except KeyboardInterrupt:
            ui.notice(console, "Interrupted. Nothing else was changed.")
        except Exception as error:  # noqa: BLE001 - keep the loop alive
            logger.debug("unhandled error in session loop", exc_info=True)
            ui.error(console, f"Unexpected error: {error}")


def main() -> None:
    logging.basicConfig(
        filename="agentic_chatbot.log",
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = get_settings()
    container = build_container(settings)
    console = ui.make_console()

    try:
        run_session(container, console)
    finally:
        container.close()
        console.print()
        console.print(ui.Text("  Database connection closed.", style=ui.MUTED))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
