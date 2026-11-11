"""Interactive session picker: timing, filtering, selection, and wiring."""

import threading
import time
from datetime import datetime, timezone

import pytest
from prompt_toolkit.input import DummyInput, create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.shortcuts import PromptSession
from rich.console import Console

from agentic_chatbot.cli import picker
from agentic_chatbot.cli.commands import dispatch
from agentic_chatbot.cli.input import PlainPrompt
from agentic_chatbot.cli.session import ChatSession
from agentic_chatbot.models import Thread


def rows(*titles):
    return [
        picker.SessionRow(
            position=index,
            thread_id=f"id-{index}",
            title=title,
            modified="1h ago",
            branch="-",
            messages=10 * index,
            active=index == 1,
        )
        for index, title in enumerate(titles, start=1)
    ]


SAMPLE = rows("Terminal UI Redesign", "Business Analytics Tools", "Tool Integration Plan")


# --- relative time -----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-11 11:59:30", "just now"),
        ("2026-11-11 11:30:00", "30m ago"),
        ("2026-11-11 11:00:00", "1h ago"),
        ("2026-11-10 18:00:00", "18h ago"),
        ("2026-11-08 12:00:00", "3d ago"),
        ("2026-09-11 12:00:00", "2mo ago"),
        ("2025-11-11 12:00:00", "1y ago"),
    ],
)
def test_relative_time_formats_ages(value, expected):
    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=timezone.utc)
    assert picker.relative_time(value, now=now) == expected


@pytest.mark.parametrize("value", [None, "", "not-a-date"])
def test_relative_time_handles_missing_or_bad_values(value):
    assert picker.relative_time(value) == "-"


# --- filtering ---------------------------------------------------------------


def test_filter_matches_case_insensitive_substring():
    assert [r.thread_id for r in picker.filter_rows(SAMPLE, "bus")] == ["id-2"]


def test_filter_with_empty_query_returns_everything():
    assert picker.filter_rows(SAMPLE, "   ") == SAMPLE


def test_filter_with_no_match_returns_empty():
    assert picker.filter_rows(SAMPLE, "zzz") == []


# --- row building ------------------------------------------------------------


class _FakeChatService:
    def __init__(self, counts):
        self._counts = counts

    def get_messages(self, thread_id):
        return [object()] * self._counts.get(thread_id, 0)


class _FakeSession:
    def __init__(self, current_thread_id, counts):
        self.current_thread_id = current_thread_id
        self.chat_service = _FakeChatService(counts)


def test_build_rows_reports_counts_time_and_active_flag():
    threads = [
        Thread("t1", "Alpha", "2026-11-11 09:00:00", "2026-11-11 10:00:00"),
        Thread("t2", "Beta", "2026-11-11 09:00:00", "2026-11-10 10:00:00"),
    ]
    session = _FakeSession("t2", {"t1": 3, "t2": 7})

    built = picker.build_rows(session, threads)

    assert [row.position for row in built] == [1, 2]
    assert [row.messages for row in built] == [3, 7]
    assert [row.active for row in built] == [False, True]
    assert built[0].branch == "-"


def test_build_rows_survives_a_failing_message_count():
    class Exploding:
        def get_messages(self, thread_id):
            raise RuntimeError("boom")

    class Session:
        current_thread_id = "t1"
        chat_service = Exploding()

    built = picker.build_rows(Session(), [Thread("t1", "Alpha", None, None)])

    assert built[0].messages == 0


# --- application wiring ------------------------------------------------------


def _build(rows):
    return picker.build_application(rows, input=DummyInput(), output=DummyOutput())


def test_building_the_picker_exposes_all_rows():
    _app, state = _build(SAMPLE)
    assert state.filtered == SAMPLE
    assert state.selected == 0


def test_typing_filters_and_resets_the_selection():
    _app, state = _build(SAMPLE)

    state.search.text = "busi"

    assert [row.thread_id for row in state.filtered] == ["id-2"]
    assert state.selected == 0


def test_selection_wraps_around():
    _app, state = _build(SAMPLE)

    state.move(-1)
    assert state.selected == len(SAMPLE) - 1
    state.move(1)
    assert state.selected == 0


def test_current_returns_none_when_nothing_matches():
    _app, state = _build(SAMPLE)
    state.search.text = "zzz"
    assert state.current() is None


# --- end-to-end keyboard drive (headless) ------------------------------------


def _drive(application, keys, timeout=6.0):
    box = {}

    def run():
        box["result"] = application.run()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout
    time.sleep(0.2)
    pipe = application.input
    pipe.send_text(keys)
    thread.join(timeout=timeout)
    if thread.is_alive():
        application.exit(result=None)
        thread.join(timeout=2)
        pytest.fail("picker did not return")
    return box.get("result")


def _drive_with_pipe(rows, keys):
    with create_pipe_input() as pipe:
        app, _state = picker.build_application(rows, input=pipe, output=DummyOutput())
        return _drive(app, keys)


def test_enter_selects_the_first_row():
    assert _drive_with_pipe(SAMPLE, "\r").thread_id == "id-1"


def test_typing_then_enter_selects_the_match():
    assert _drive_with_pipe(SAMPLE, "busi\r").thread_id == "id-2"


def test_down_arrow_then_enter_selects_the_next_row():
    assert _drive_with_pipe(SAMPLE, "\x1b[B\r").thread_id == "id-2"


def test_escape_cancels():
    assert _drive_with_pipe(SAMPLE, "\x1b") is None


# --- fallback + handler wiring -----------------------------------------------


def test_supports_interactive_detects_real_prompt_sessions():
    real = PromptSession(input=DummyInput(), output=DummyOutput())
    assert picker.supports_interactive(real) is True
    assert picker.supports_interactive(PlainPrompt()) is False


def test_pick_returns_none_when_the_application_cannot_run(monkeypatch):
    class Session:
        console = Console(width=80, record=True)
        current_thread_id = "t1"

        class thread_service:
            @staticmethod
            def get_thread(thread_id):
                return None

    monkeypatch.setattr(
        picker, "_run_picker", lambda *a, **k: (_ for _ in ()).throw(OSError("no tty"))
    )

    assert picker.pick(Session(), [Thread("t1", "Alpha", None, None)]) is None


def test_threads_handler_switches_to_the_picked_thread(container):
    alpha = container.thread_service.create_thread("Alpha")
    beta = container.thread_service.create_thread("Beta")
    console = Console(width=100, record=True)
    session = ChatSession(
        container=container, console=console, current_thread_id=alpha.thread_id
    )
    session.pick = lambda _session, _threads: container.thread_service.get_thread(
        beta.thread_id
    )

    dispatch(session, "/threads")

    assert session.current_thread_id == beta.thread_id
    assert "Switched to Beta" in console.export_text()


def test_threads_handler_default_pick_is_the_static_list(container):
    alpha = container.thread_service.create_thread("Alpha")
    container.thread_service.create_thread("Beta")
    console = Console(width=100, record=True)
    session = ChatSession(
        container=container, console=console, current_thread_id=alpha.thread_id
    )

    dispatch(session, "/threads")

    assert session.current_thread_id == alpha.thread_id
    text = console.export_text()
    assert "Alpha" in text and "Beta" in text and "active" in text


def test_threads_handler_notes_already_active(container):
    alpha = container.thread_service.create_thread("Alpha")
    console = Console(width=100, record=True)
    session = ChatSession(
        container=container, console=console, current_thread_id=alpha.thread_id
    )
    session.pick = lambda _session, _threads: container.thread_service.get_thread(
        alpha.thread_id
    )

    dispatch(session, "/threads")

    assert "Already in Alpha" in console.export_text()


def test_delete_handler_uses_the_picker_when_no_id(container):
    alpha = container.thread_service.create_thread("Alpha")
    beta = container.thread_service.create_thread("Beta")
    console = Console(width=100, record=True)
    session = ChatSession(
        container=container, console=console, current_thread_id=alpha.thread_id
    )
    session.pick = lambda _session, _threads: container.thread_service.get_thread(
        beta.thread_id
    )
    session.ask = lambda *_args, **_kwargs: "y"

    dispatch(session, "/delete")

    assert not container.thread_service.thread_exists(beta.thread_id)
    assert session.current_thread_id == alpha.thread_id


def test_delete_handler_cancels_when_picker_returns_none(container):
    alpha = container.thread_service.create_thread("Alpha")
    console = Console(width=100, record=True)
    session = ChatSession(
        container=container, console=console, current_thread_id=alpha.thread_id
    )
    session.pick = lambda _session, _threads: None

    dispatch(session, "/delete")

    assert container.thread_service.thread_exists(alpha.thread_id)
