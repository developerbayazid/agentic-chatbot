"""The document retrieval tools exposed to the model."""

import json
from types import SimpleNamespace

import pytest

from agentic_chatbot.database import create_connection, init_schema
from agentic_chatbot.repository import DocumentsRepository
from agentic_chatbot.services.document_service import DocumentService
from agentic_chatbot.tools.documents import create_document_tools
from agentic_chatbot.vector_store import VectorIndexStore
from tests.fakes import FakeEmbeddings


@pytest.fixture
def rag(tmp_path):
    connection = create_connection(str(tmp_path / "tools.db"))
    init_schema(connection)
    embeddings = FakeEmbeddings(dimensions=8)
    service = DocumentService(
        DocumentsRepository(connection),
        VectorIndexStore(tmp_path / "faiss", dimensions=8),
        embeddings,
        chunk_size=100,
        chunk_overlap=10,
    )
    document = tmp_path / "handbook.md"
    document.write_text("onboarding starts on monday", encoding="utf-8")
    service.ingest_path(document, "handbook")

    try:
        yield SimpleNamespace(
            tools={tool.name: tool for tool in create_document_tools(service)},
            service=service,
            embeddings=embeddings,
        )
    finally:
        connection.close()


def test_search_documents_returns_structured_hits(rag):
    payload = json.loads(
        rag.tools["search_documents"].invoke(
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


def test_search_documents_requires_a_query(rag):
    assert rag.tools["search_documents"].invoke({"query": "   "}) == (
        "Error: query is required."
    )


def test_search_documents_reports_no_matches(rag):
    rag.service._min_score = 0.99

    payload = json.loads(
        rag.tools["search_documents"].invoke(
            {"query": "nothing matches this", "namespace": "handbook"}
        )
    )

    assert payload["count"] == 0
    assert payload["results"] == []
    assert "No matching documents" in payload["message"]


def test_search_documents_rejects_an_unknown_namespace(rag):
    payload = json.loads(
        rag.tools["search_documents"].invoke(
            {
                "query": "two major phases of a typical RAG system",
                "namespace": "AI Engineering Handbook",
            }
        )
    )

    assert payload["count"] == 0
    assert payload["results"] == []
    assert payload["error"] == "Unknown namespace."
    assert payload["namespaces"] == ["handbook"]
    assert rag.embeddings.embed_query_calls == 0


def test_search_documents_empty_namespace_searches_everything(rag):
    payload = json.loads(
        rag.tools["search_documents"].invoke(
            {"query": "onboarding starts on monday"}
        )
    )

    assert payload["count"] == 1
    assert payload["namespace"] is None
    assert payload["results"][0]["namespace"] == "handbook"


def test_list_documents_reports_namespaces(rag):
    payload = json.loads(rag.tools["list_documents"].invoke({}))

    assert payload["namespaces"] == ["handbook"]
    assert payload["count"] == 1
    assert payload["documents"][0]["source"].endswith("handbook.md")


def test_list_documents_can_filter_by_namespace(rag):
    payload = json.loads(
        rag.tools["list_documents"].invoke({"namespace": "other"})
    )

    assert payload["count"] == 0


def test_tool_schemas_expose_only_model_arguments(rag):
    assert rag.tools["search_documents"].args == {
        "query": {"title": "Query", "type": "string"},
        "namespace": {"default": "", "title": "Namespace", "type": "string"},
        "k": {"default": 4, "title": "K", "type": "integer"},
    }
    assert rag.tools["list_documents"].args == {
        "namespace": {"default": "", "title": "Namespace", "type": "string"}
    }
