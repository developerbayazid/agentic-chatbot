"""The document retrieval tools exposed to the model."""

import json

import pytest

from agentic_chatbot.database import create_connection, init_schema
from agentic_chatbot.repository import DocumentsRepository
from agentic_chatbot.services.document_service import DocumentService
from agentic_chatbot.tools.documents import create_document_tools
from agentic_chatbot.vector_store import VectorIndexStore
from tests.fakes import FakeEmbeddings


@pytest.fixture
def tools(tmp_path):
    connection = create_connection(str(tmp_path / "tools.db"))
    init_schema(connection)
    service = DocumentService(
        DocumentsRepository(connection),
        VectorIndexStore(tmp_path / "faiss", dimensions=8),
        FakeEmbeddings(dimensions=8),
        chunk_size=100,
        chunk_overlap=10,
    )
    document = tmp_path / "handbook.md"
    document.write_text("onboarding starts on monday", encoding="utf-8")
    service.ingest_path(document, "handbook")

    try:
        yield {tool.name: tool for tool in create_document_tools(service)}
    finally:
        connection.close()


def test_search_documents_returns_structured_hits(tools):
    payload = json.loads(
        tools["search_documents"].invoke(
            {"query": "onboarding starts on monday", "namespace": "handbook"}
        )
    )

    assert payload["count"] == 1
    result = payload["results"][0]
    assert result["namespace"] == "handbook"
    assert result["title"] == "handbook"
    assert result["page"] is None
    assert "score" in result
    assert result["content"] == "onboarding starts on monday"


def test_search_documents_requires_a_query(tools):
    assert tools["search_documents"].invoke({"query": "   "}) == (
        "Error: query is required."
    )


def test_search_documents_reports_no_matches(tools):
    payload = json.loads(
        tools["search_documents"].invoke(
            {"query": "nothing matches this", "namespace": "other"}
        )
    )

    assert payload["count"] == 0
    assert payload["results"] == []
    assert "No matching documents" in payload["message"]


def test_list_documents_reports_namespaces(tools):
    payload = json.loads(tools["list_documents"].invoke({}))

    assert payload["namespaces"] == ["handbook"]
    assert payload["count"] == 1
    assert payload["documents"][0]["source"].endswith("handbook.md")


def test_list_documents_can_filter_by_namespace(tools):
    payload = json.loads(tools["list_documents"].invoke({"namespace": "other"}))

    assert payload["count"] == 0


def test_tool_schemas_expose_only_model_arguments(tools):
    assert tools["search_documents"].args == {
        "query": {"title": "Query", "type": "string"},
        "namespace": {"default": "", "title": "Namespace", "type": "string"},
        "k": {"default": 4, "title": "K", "type": "integer"},
    }
    assert tools["list_documents"].args == {
        "namespace": {"default": "", "title": "Namespace", "type": "string"}
    }
