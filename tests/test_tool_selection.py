"""Tool-selection routing, execution, and honest tool-result handling."""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from agentic_chatbot.container import TOOL_GUIDANCE
from agentic_chatbot.database import create_connection, init_schema
from agentic_chatbot.graph.workflow import build_chatbot
from agentic_chatbot.repository import DocumentsRepository, NotesRepository
from agentic_chatbot.services.document_service import DocumentService
from agentic_chatbot.tools import calculator
from agentic_chatbot.tools.documents import create_document_tools
from agentic_chatbot.tools.notes import create_note_tools
from agentic_chatbot.tools.utilities import summarize_text
from agentic_chatbot.vector_store import VectorIndexStore
from tests.fakes import FakeEmbeddings

CONFIG = {"configurable": {"thread_id": "thread-1"}}
DOCUMENT_TEXT = (
    "A RAG system has two major phases: retrieval and generation."
)


class ScriptedLLM:
    """Deterministic stand-in for the model's tool-selection decision."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(list(messages))

        if self.responses:
            return self.responses.pop(0)

        return AIMessage(content="Done.")


def tool_call(name, args, call_id="call-1"):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id}],
    )


def run(llm, tools, text):
    graph = build_chatbot(llm, InMemorySaver(), tools)
    return graph.invoke(
        {"messages": [HumanMessage(content=text)]},
        config=CONFIG,
    )


def tool_messages(result):
    return [
        message
        for message in result["messages"]
        if isinstance(message, ToolMessage)
    ]


@pytest.fixture
def documents(tmp_path):
    connection = create_connection(str(tmp_path / "selection.db"))
    init_schema(connection)
    service = DocumentService(
        DocumentsRepository(connection),
        VectorIndexStore(tmp_path / "faiss", dimensions=8),
        FakeEmbeddings(dimensions=8),
        chunk_size=500,
        chunk_overlap=20,
    )
    source = tmp_path / "handbook.md"
    source.write_text(DOCUMENT_TEXT, encoding="utf-8")
    service.ingest_path(source, "default")

    try:
        yield SimpleNamespace(
            tools=create_document_tools(service),
            service=service,
        )
    finally:
        connection.close()


@pytest.fixture
def notes(tmp_path):
    connection = create_connection(str(tmp_path / "notes.db"))
    init_schema(connection)
    repository = NotesRepository(connection)
    repository.create(
        "thread-1",
        "Python tips",
        "Use dataclasses for small value objects.",
    )

    try:
        yield create_note_tools(repository)
    finally:
        connection.close()


def test_general_knowledge_does_not_call_tools(documents):
    llm = ScriptedLLM(
        AIMessage(content="RAG combines retrieval with generation.")
    )

    result = run(
        llm,
        [calculator, *documents.tools],
        "What is RAG?",
    )

    assert tool_messages(result) == []
    assert len(llm.calls) == 1
    assert result["messages"][-1].content == (
        "RAG combines retrieval with generation."
    )


def test_explicit_document_question_executes_search_documents(documents):
    documents.service._min_score = -1.0
    llm = ScriptedLLM(
        tool_call(
            "search_documents",
            {"query": "two major phases of a RAG system"},
        ),
        AIMessage(
            content=(
                "According to the handbook, retrieval and generation are the "
                "two major phases."
            )
        ),
    )

    result = run(
        llm,
        documents.tools,
        "According to my AI Engineering Handbook, what are the phases?",
    )

    messages = tool_messages(result)
    assert len(messages) == 1
    assert messages[0].name == "search_documents"

    payload = json.loads(messages[0].content)
    assert payload["count"] == 1
    assert DOCUMENT_TEXT in payload["results"][0]["content"]

    assert any(isinstance(item, ToolMessage) for item in llm.calls[1])
    assert result["messages"][-1].content.startswith("According to the handbook")


def test_notes_question_executes_search_notes(notes):
    llm = ScriptedLLM(
        tool_call("search_notes", {"query": "Python"}),
        AIMessage(content="Your Python note says to use dataclasses."),
    )

    result = run(llm, notes, "Find my saved notes about Python.")

    messages = tool_messages(result)
    assert len(messages) == 1
    assert messages[0].name == "search_notes"

    payload = json.loads(messages[0].content)
    assert payload["count"] == 1
    assert payload["notes"][0]["title"] == "Python tips"
    assert result["messages"][-1].content == (
        "Your Python note says to use dataclasses."
    )


def test_calculator_question_executes_calculator():
    llm = ScriptedLLM(
        tool_call("calculator", {"expression": "250 * 12"}),
        AIMessage(content="250 * 12 = 3000."),
    )

    result = run(llm, [calculator], "Calculate 250 * 12.")

    messages = tool_messages(result)
    assert len(messages) == 1
    assert messages[0].name == "calculator"
    assert messages[0].content == "3000"
    assert result["messages"][-1].content == "250 * 12 = 3000."


def test_tool_failure_is_returned_to_the_model():
    llm = ScriptedLLM(
        tool_call("calculator", {"expression": "2 +"}),
        AIMessage(content="I could not evaluate that expression."),
    )

    result = run(llm, [calculator], "Calculate 2 +.")

    messages = tool_messages(result)
    assert len(messages) == 1
    assert messages[0].content.startswith("Error:")
    assert any(isinstance(item, ToolMessage) for item in llm.calls[1])
    assert result["messages"][-1].content == (
        "I could not evaluate that expression."
    )


def test_empty_retrieval_is_reported_to_the_model(documents):
    documents.service._min_score = 0.99
    llm = ScriptedLLM(
        tool_call("search_documents", {"query": "unrelated topic"}),
        AIMessage(content="I could not find that in your documents."),
    )

    result = run(llm, documents.tools, "Search my documents for unrelated topic.")

    messages = tool_messages(result)
    assert len(messages) == 1

    payload = json.loads(messages[0].content)
    assert payload["count"] == 0
    assert "No matching documents" in payload["message"]
    assert result["messages"][-1].content == (
        "I could not find that in your documents."
    )


def test_tool_guidance_covers_selection_rules():
    assert "Do not call tools for ordinary general-knowledge questions" in (
        TOOL_GUIDANCE
    )
    assert "search_documents" in TOOL_GUIDANCE
    assert "search_notes" in TOOL_GUIDANCE
    assert "Never claim to have searched" in TOOL_GUIDANCE


def test_tool_descriptions_state_when_to_use(documents, notes):
    tools = {
        tool.name: tool for tool in [calculator, *documents.tools, *notes]
    }

    assert "general-knowledge" in tools["search_documents"].description
    assert "uploaded or" in tools["search_documents"].description
    assert "documents or namespaces exist" in tools["list_documents"].description
    assert "notes" in tools["search_notes"].description
    assert "notes" in tools["list_notes"].description
    assert "arithmetic" in tools["calculator"].description
    assert "search_documents" in summarize_text.description
