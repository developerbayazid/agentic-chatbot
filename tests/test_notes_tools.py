import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from agentic_chatbot.graph.workflow import build_chatbot
from agentic_chatbot.repository import NotesRepository
from agentic_chatbot.tools.notes import create_note_tools
from tests.pg import connect

THREAD_A = {"configurable": {"thread_id": "thread-a"}}
THREAD_B = {"configurable": {"thread_id": "thread-b"}}


def _make_tools(schema):
    from agentic_chatbot.postgres import init_schema

    connection = connect(schema)
    # Each connection must initialise its own schema: without this the queries
    # fall through `search_path` to the `public` tables.
    init_schema(connection, embedding_dimensions=8)
    repository = NotesRepository(connection)
    tools = {
        note_tool.name: note_tool
        for note_tool in create_note_tools(repository)
    }
    return connection, repository, tools


@pytest.fixture
def note_context(schema):
    connection, repository, tools = _make_tools(schema)

    try:
        yield repository, tools
    finally:
        connection.close()


def _call(tools, name, payload, config=THREAD_A):
    return json.loads(tools[name].invoke(payload, config=config))


def test_note_lifecycle_round_trip(note_context):
    _, tools = note_context

    saved = _call(
        tools,
        "save_note",
        {"title": "Grocery list", "content": "Milk, eggs, spinach"},
    )

    assert saved["title"] == "Grocery list"
    assert saved["thread_id"] == "thread-a"

    listed = _call(tools, "list_notes", {})
    assert any(note["note_id"] == saved["note_id"] for note in listed["notes"])

    matches = _call(tools, "search_notes", {"query": "spinach"})
    assert any(note["note_id"] == saved["note_id"] for note in matches["notes"])

    deleted = _call(tools, "delete_note", {"note_id": saved["note_id"]})
    assert deleted["deleted"] == saved["note_id"]

    remaining = _call(tools, "search_notes", {"query": "spinach"})
    assert all(
        note["note_id"] != saved["note_id"] for note in remaining["notes"]
    )


def test_notes_are_private_to_each_thread(note_context):
    _, tools = note_context

    saved = _call(
        tools,
        "save_note",
        {"title": "Thread A secret", "content": "only A should see this"},
    )

    listed_b = _call(tools, "list_notes", {}, config=THREAD_B)
    assert listed_b["count"] == 0

    searched_b = _call(
        tools, "search_notes", {"query": "secret"}, config=THREAD_B
    )
    assert searched_b["count"] == 0

    delete_from_b = tools["delete_note"].invoke(
        {"note_id": saved["note_id"]}, config=THREAD_B
    )
    assert delete_from_b.startswith("Error:")

    still_there = _call(tools, "search_notes", {"query": "secret"})
    assert still_there["count"] == 1


def test_note_tools_require_conversation_context(note_context):
    _, tools = note_context

    assert tools["list_notes"].invoke({}).startswith("Error:")
    assert tools["save_note"].invoke(
        {"title": "No context", "content": "body"}
    ).startswith("Error:")


def test_thread_config_is_not_exposed_to_model(note_context):
    _, tools = note_context

    assert tools["save_note"].args == {
        "title": {"title": "Title", "type": "string"},
        "content": {"title": "Content", "type": "string"},
    }
    assert tools["list_notes"].args == {}


class SaveNoteLLM:
    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1

        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "save_note",
                        "args": {"title": "From graph", "content": "body"},
                        "id": "call-1",
                    }
                ],
            )

        return AIMessage(content="Saved.")


def test_graph_forwards_thread_id_to_note_tools(note_context):
    repository, _ = note_context
    graph = build_chatbot(
        SaveNoteLLM(),
        InMemorySaver(),
        create_note_tools(repository),
    )

    graph.invoke(
        {"messages": [HumanMessage(content="save a note")]},
        config=THREAD_A,
    )

    saved = repository.list_all("thread-a")
    assert [note.title for note in saved] == ["From graph"]
    assert repository.list_all("thread-b") == []


def test_notes_persist_across_connections(schema):
    first_connection, _, first_tools = _make_tools(schema)
    saved = _call(
        first_tools,
        "save_note",
        {"title": "Durable note", "content": "survives restarts"},
    )
    first_connection.close()

    second_connection, _, second_tools = _make_tools(schema)

    try:
        listed = _call(second_tools, "list_notes", {})
        assert any(
            note["note_id"] == saved["note_id"] for note in listed["notes"]
        )
    finally:
        second_connection.close()


def test_save_note_requires_title(note_context):
    _, tools = note_context

    assert tools["save_note"].invoke(
        {"title": "  ", "content": "body"}, config=THREAD_A
    ).startswith("Error:")


def test_search_notes_requires_query(note_context):
    _, tools = note_context

    assert tools["search_notes"].invoke(
        {"query": "   "}, config=THREAD_A
    ).startswith("Error:")


def test_delete_missing_note_reports_error(note_context):
    _, tools = note_context

    assert tools["delete_note"].invoke(
        {"note_id": "missing"}, config=THREAD_A
    ).startswith("Error:")
