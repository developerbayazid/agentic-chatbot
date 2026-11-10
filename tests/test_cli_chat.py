"""Assistant turn rendering: streaming, tool visibility, and errors."""

import pytest
from rich.console import Console

from agentic_chatbot.cli import console as ui
from agentic_chatbot.cli.chat import process_message
from agentic_chatbot.models import TurnEvent


class FakeChatService:
    def __init__(self, events=None, error=None):
        self.events = events or []
        self.error = error
        self.calls = []

    def stream_turn(self, thread_id, user_message):
        self.calls.append((thread_id, user_message))
        if self.error is not None:
            raise self.error

        for event in self.events:
            yield event


@pytest.fixture
def console():
    return Console(width=100, record=True)


def run(console, service):
    process_message(console, service, "thread-1", "hi")
    return console.export_text()


def test_streams_tokens_between_user_and_assistant_headers(console):
    service = FakeChatService(
        events=[
            TurnEvent(type="token", content="Hello"),
            TurnEvent(type="token", content=" world"),
            TurnEvent(type="done"),
        ]
    )

    text = run(console, service)

    assert "YOU" in text
    assert "hi" in text
    assert "BAYAZID AI" in text
    assert "Hello world" in text


def test_user_label_precedes_the_message(console):
    service = FakeChatService(events=[TurnEvent(type="done")])

    text = run(console, service)

    assert text.index("YOU") < text.index("hi")


def test_renders_tool_call_and_result(console):
    service = FakeChatService(
        events=[
            TurnEvent(type="tool_call", name="calculator", content='{"expression": "2+2"}'),
            TurnEvent(type="tool_result", name="calculator", content="4"),
            TurnEvent(type="token", content="The answer is 4."),
            TurnEvent(type="done"),
        ]
    )

    text = run(console, service)

    assert "calculator" in text
    assert "The answer is 4." in text


def test_tool_results_do_not_dump_raw_payloads(console):
    long_result = "x" * 500
    service = FakeChatService(
        events=[
            TurnEvent(type="tool_result", name="tool", content=long_result),
            TurnEvent(type="done"),
        ]
    )

    text = run(console, service)

    assert "Completed" in text
    assert long_result not in text


def test_shows_generated_title_on_first_turn(console):
    service = FakeChatService(
        events=[
            TurnEvent(type="token", content="Hi"),
            TurnEvent(type="done", title="Greeting"),
        ]
    )

    text = run(console, service)

    assert "Conversation title: Greeting" in text


def test_reports_error_without_raising(console):
    service = FakeChatService(error=RuntimeError("boom"))

    text = run(console, service)

    assert "Could not complete this response" in text
    assert "boom" in text


def test_does_not_print_tracebacks_to_the_user(console):
    service = FakeChatService(error=ValueError("secret detail"))

    text = run(console, service)

    assert "Traceback" not in text


def test_interrupt_propagates_for_the_loop_to_handle(console):
    service = FakeChatService(error=KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        process_message(console, service, "thread-1", "hi")


def test_uses_the_given_thread_and_message(console):
    service = FakeChatService(events=[TurnEvent(type="done")])

    process_message(console, service, "thread-9", "hello there")

    assert service.calls == [("thread-9", "hello there")]


def test_empty_turn_still_closes_cleanly(console):
    service = FakeChatService(events=[TurnEvent(type="done")])

    text = run(console, service)

    assert "BAYAZID AI" in text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("```python\nprint(1)\n```", True),
        ("### Heading", True),
        ("- a bullet", True),
        ("1. numbered", True),
        ("> a quote", True),
        ("| a | b |\n| - | - |", True),
        ("---", True),
        ("Hello! I'm doing well.", False),
        ("The answer is 4.", False),
    ],
)
def test_markdown_detection(text, expected):
    from agentic_chatbot.cli.chat import looks_like_markdown

    assert looks_like_markdown(text) is expected


def test_plain_prose_streams_incrementally(console):
    service = FakeChatService(
        events=[
            TurnEvent(type="token", content="Hello"),
            TurnEvent(type="token", content=" there"),
            TurnEvent(type="done"),
        ]
    )

    text = run(console, service)

    assert "Hello there" in text


def test_markdown_response_still_prints_its_content(console):
    service = FakeChatService(
        events=[
            TurnEvent(type="token", content="### Summary\n"),
            TurnEvent(type="token", content="- first point\n- second point"),
            TurnEvent(type="done"),
        ]
    )

    text = run(console, service)

    assert "Summary" in text
    assert "first point" in text
    assert "second point" in text


def test_tool_activity_flushes_buffered_prose_before_the_tool(console):
    service = FakeChatService(
        events=[
            TurnEvent(type="token", content="Let me check."),
            TurnEvent(type="tool_call", name="calculator", content="{}"),
            TurnEvent(type="tool_result", name="calculator", content="4"),
            TurnEvent(type="done"),
        ]
    )

    text = run(console, service)

    assert text.index("Let me check.") < text.index("calculator")


def test_buffered_prose_survives_a_midstream_error(console):
    class BrokenService:
        def stream_turn(self, thread_id, user_message):
            yield TurnEvent(type="token", content="partial answer")
            raise RuntimeError("network died")

    text = run(console, BrokenService())

    assert "partial answer" in text
    assert "Could not complete this response" in text


# --- message presentation ----------------------------------------------------


def test_user_message_uses_a_you_label(console):
    ui.user_message(console, "hello there")

    text = console.export_text()
    assert "YOU" in text
    assert "hello there" in text
    assert text.index("YOU") < text.index("hello there")


def test_assistant_header_uses_the_app_name(console):
    ui.assistant_header(console)

    assert "BAYAZID AI" in console.export_text()


def test_multiline_user_input_is_preserved(console):
    ui.user_message(console, "first line\nsecond line")

    text = console.export_text()
    assert "first line" in text
    assert "second line" in text


def test_tool_call_shows_the_tool_name_and_state(console):
    ui.tool_call(console, "get_weather", '{"location": "Dhaka"}')

    text = console.export_text()
    assert "get_weather" in text
    assert "running" in text


def test_tool_result_reports_completion(console):
    ui.tool_result(console, "get_weather", '{"temperature": 27}')

    assert "Completed" in console.export_text()


def test_tool_result_detects_an_error_payload(console):
    ui.tool_result(console, "get_weather", "Error: city not found")

    assert "Failed" in console.export_text()


def test_tool_result_detects_a_failed_status(console):
    ui.tool_result(console, "tool", "failed to connect")

    assert "Failed" in console.export_text()


def test_tool_call_and_result_are_indented_under_the_assistant(console):
    ui.assistant_header(console)
    ui.tool_call(console, "calculator", "{}")
    ui.tool_result(console, "calculator", "4")

    rows = [line for line in console.export_text().splitlines() if line.strip()]
    assert rows[1].startswith("  ")
    assert rows[2].startswith("    ")


def test_error_rendering_is_inline_without_a_box(console):
    ui.error(console, "Something broke\nretry later")

    text = console.export_text()
    assert "Something broke" in text
    assert "retry later" in text


def test_transcript_has_no_heavy_borders(console):
    ui.user_message(console, "hi")
    ui.assistant_header(console)
    ui.tool_call(console, "tool", "{}")
    ui.tool_result(console, "tool", "ok")
    ui.stream_token(console, "answer")

    text = console.export_text()
    for box in "╭╮╰╯│┌┐└┘":
        assert box not in text


@pytest.mark.parametrize("width", [60, 80, 100, 120])
def test_transcript_wraps_without_overflow(width):
    console = Console(width=width, record=True)

    ui.user_message(console, "word " * 60)
    ui.assistant_header(console)
    ui.stream_token(console, "answer " * 40)

    for line in console.export_text().splitlines():
        assert len(line) <= width, line
