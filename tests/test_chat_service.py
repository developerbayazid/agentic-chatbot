import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from agentic_chatbot.models import TurnEvent
from agentic_chatbot.services.chat_service import ChatService
from tests.fakes import (
    FakeChatbot,
    FakeThreadService,
    FakeTitleService,
    message_chunk,
)


def build_service(chatbot=None, threads=None, titles=None, prompt="You are helpful."):
    return ChatService(
        chatbot if chatbot is not None else FakeChatbot(),
        threads if threads is not None else FakeThreadService(),
        titles if titles is not None else FakeTitleService(),
        prompt,
    )


def test_first_turn_streams_tokens_and_generates_title():
    chatbot = FakeChatbot(
        chunks=[message_chunk("Hel"), message_chunk("lo")]
    )
    threads = FakeThreadService()
    titles = FakeTitleService("Greeting")
    service = build_service(chatbot, threads, titles, prompt="Be nice.")

    events = list(service.stream_turn("thread-1", "hi"))

    assert [event.content for event in events if event.type == "token"] == [
        "Hel",
        "lo",
    ]
    assert events[-1] == TurnEvent(type="done", title="Greeting")
    assert titles.calls == ["hi"]
    assert threads.renamed == [("thread-1", "Greeting")]
    assert threads.touched == []


def test_first_turn_sends_system_message_and_user_message():
    chatbot = FakeChatbot()
    service = build_service(chatbot, prompt="Be nice.")

    list(service.stream_turn("thread-1", "hi"))

    messages = chatbot.last_inputs["messages"]
    assert isinstance(messages[0], SystemMessage)
    assert messages[0].content == "Be nice."
    assert isinstance(messages[1], HumanMessage)
    assert messages[1].content == "hi"


def test_first_turn_uses_expected_stream_arguments():
    chatbot = FakeChatbot()
    service = build_service(chatbot)

    list(service.stream_turn("thread-1", "hi"))

    assert chatbot.last_stream_kwargs["config"] == {
        "configurable": {"thread_id": "thread-1"}
    }
    assert chatbot.last_stream_kwargs["stream_mode"] == "messages"
    assert chatbot.last_stream_kwargs["version"] == "v2"


def test_subsequent_turn_skips_system_message_and_title():
    chatbot = FakeChatbot(messages=[HumanMessage(content="earlier")])
    threads = FakeThreadService()
    titles = FakeTitleService()
    service = build_service(chatbot, threads, titles)

    events = list(service.stream_turn("thread-1", "again"))

    assert len(chatbot.last_inputs["messages"]) == 1
    assert isinstance(chatbot.last_inputs["messages"][0], HumanMessage)
    assert titles.calls == []
    assert threads.renamed == []
    assert threads.touched == ["thread-1"]
    assert events[-1] == TurnEvent(type="done", title=None)


def test_non_message_and_non_string_chunks_are_ignored():
    chatbot = FakeChatbot(
        chunks=[
            {"type": "updates", "data": (object(), {})},
            message_chunk(""),
            message_chunk(42),
            message_chunk("ok"),
        ]
    )
    service = build_service(chatbot)

    events = list(service.stream_turn("thread-1", "hi"))

    assert [event.content for event in events if event.type == "token"] == ["ok"]
    assert events[-1].type == "done"


def test_get_messages_returns_checkpointed_state():
    chatbot = FakeChatbot(messages=[HumanMessage(content="hello")])
    service = build_service(chatbot)

    assert service.get_messages("thread-1") == [HumanMessage(content="hello")]
    assert chatbot.last_config == {"configurable": {"thread_id": "thread-1"}}


def test_stream_errors_propagate():
    chatbot = FakeChatbot(error=RuntimeError("boom"))
    service = build_service(chatbot)

    with pytest.raises(RuntimeError, match="boom"):
        list(service.stream_turn("thread-1", "hi"))


def test_first_turn_persists_generated_title(container):
    chatbot = FakeChatbot()
    service = ChatService(
        chatbot,
        container.thread_service,
        FakeTitleService("Persisted Title"),
        "You are helpful.",
    )
    thread = container.thread_service.create_thread()

    list(service.stream_turn(thread.thread_id, "hello"))

    assert (
        container.thread_service.get_thread(thread.thread_id).title
        == "Persisted Title"
    )
