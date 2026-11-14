"""Hybrid retrieval: parallel vector + BM25 search fused with RRF."""

import threading

import pytest

from agentic_chatbot.bm25_store import BM25IndexStore
from agentic_chatbot.database import create_connection, init_schema
from agentic_chatbot.repository import DocumentsRepository
from agentic_chatbot.services.document_service import (
    DocumentService,
    RetrievalError,
)
from agentic_chatbot.vector_store import VectorIndexStore
from tests.fakes import FakeEmbeddings


class RecordingEmbeddings(FakeEmbeddings):
    def __init__(self, dimensions=8):
        super().__init__(dimensions)
        self.queries = []

    def embed_query(self, text):
        self.queries.append(text)
        return super().embed_query(text)


class RecordingBM25Store(BM25IndexStore):
    def __init__(self, repository):
        super().__init__(repository)
        self.queries = []

    def search(self, namespaces, query, k):
        self.queries.append(query)
        return super().search(namespaces, query, k)


@pytest.fixture
def hybrid(tmp_path):
    connection = create_connection(str(tmp_path / "hybrid.db"))
    init_schema(connection)
    repository = DocumentsRepository(connection)
    embeddings = RecordingEmbeddings(dimensions=8)
    bm25 = RecordingBM25Store(repository)
    service = DocumentService(
        repository,
        VectorIndexStore(tmp_path / "faiss", dimensions=8),
        embeddings,
        chunk_size=200,
        chunk_overlap=0,
        top_k=4,
        min_score=0.15,
        bm25_store=bm25,
        search_mode="hybrid",
        vector_candidates=10,
        bm25_candidates=10,
        rrf_k=60,
    )

    try:
        yield service, repository, embeddings, bm25, tmp_path
    finally:
        connection.close()


def _ingest(service, root, name, text, namespace):
    path = root / name
    path.write_text(text, encoding="utf-8")
    service.ingest_path(path, namespace)
    return path


def test_both_retrievers_contribute_to_the_fused_results(hybrid):
    service, _, _, _, root = hybrid
    _ingest(
        service,
        root,
        "handbook.md",
        "onboarding starts on monday",
        "handbook",
    )
    _ingest(
        service,
        root,
        "finance.md",
        "quarterly revenue figures",
        "handbook",
    )

    hits = service.search_hybrid("onboarding", "handbook", k=4)
    contents = {hit.content for hit in hits}

    # "onboarding" is an exact BM25 match; the finance chunk has no query term
    # but is still a vector candidate, so both retrievers contribute.
    assert "onboarding starts on monday" in contents
    assert "quarterly revenue figures" in contents


def test_the_same_query_reaches_both_retrievers(hybrid):
    service, _, embeddings, bm25, root = hybrid
    _ingest(service, root, "handbook.md", "onboarding starts on monday", "ns")

    service.search_hybrid("  onboarding  ", "ns", k=4)

    assert embeddings.queries == ["  onboarding  "]
    assert bm25.queries == ["  onboarding  "]


def test_namespace_filtering_is_respected(hybrid):
    service, _, _, _, root = hybrid
    _ingest(service, root, "a.md", "shared keyword alpha", "alpha")
    _ingest(service, root, "b.md", "shared keyword beta", "beta")

    hits = service.search_hybrid("shared keyword", "alpha", k=4)

    assert hits
    assert {hit.namespace for hit in hits} == {"alpha"}


def test_hybrid_search_across_all_namespaces(hybrid):
    service, _, _, _, root = hybrid
    _ingest(service, root, "a.md", "shared keyword alpha", "alpha")
    _ingest(service, root, "b.md", "shared keyword beta", "beta")

    hits = service.search_hybrid("shared keyword", None, k=4)

    assert {hit.namespace for hit in hits} == {"alpha", "beta"}


def test_retrievers_run_concurrently(hybrid, monkeypatch):
    service, repository, _, _, root = hybrid
    _ingest(service, root, "a.md", "alpha text", "ns")
    _ingest(service, root, "b.md", "beta text", "ns")
    documents = service.list_documents()
    first = repository.chunk_ids(documents[0].doc_id)[0]
    second = repository.chunk_ids(documents[1].doc_id)[0]
    chunk_rows = repository.chunks_by_ids([first, second])
    barrier = threading.Barrier(2, timeout=5)

    def vector(query, namespaces, candidates, allow_failure=False):
        barrier.wait()
        return [first], {first: 0.9}

    def bm25(query, namespaces, candidates, allow_failure=False):
        barrier.wait()
        return [second], {second: 4.0}

    monkeypatch.setattr(service, "_retrieve_vector", vector)
    monkeypatch.setattr(service, "_retrieve_bm25", bm25)

    fused = service._hybrid_search("query", ["ns"], limit=4)

    # Both workers had to reach the barrier for this to return, and both
    # rankings are represented in the fused output.
    assert {hit.chunk_id for hit in fused} == {
        chunk_rows[first]["chunk_id"],
        chunk_rows[second]["chunk_id"],
    }




def test_vector_failure_falls_back_to_bm25(hybrid, monkeypatch):
    service, _, embeddings, _, root = hybrid
    _ingest(service, root, "handbook.md", "onboarding starts on monday", "ns")

    def boom(_text):
        raise RuntimeError("embedding service down")

    monkeypatch.setattr(embeddings, "embed_query", boom)

    hits = service.search_hybrid("onboarding", "ns", k=4)

    assert [hit.content for hit in hits] == ["onboarding starts on monday"]
    assert hits[0].vector_score is None
    assert hits[0].bm25_score is not None


def test_bm25_failure_falls_back_to_vector(hybrid, monkeypatch):
    service, _, _, bm25, root = hybrid
    _ingest(service, root, "handbook.md", "onboarding starts on monday", "ns")

    def boom(*args, **kwargs):
        raise RuntimeError("bm25 down")

    monkeypatch.setattr(bm25, "search", boom)

    hits = service.search_hybrid("onboarding", "ns", k=4)

    assert [hit.content for hit in hits] == ["onboarding starts on monday"]
    assert hits[0].vector_score is not None
    assert hits[0].bm25_score is None


def test_both_retrievers_failing_is_surfaced(hybrid, monkeypatch):
    service, _, embeddings, bm25, root = hybrid
    _ingest(service, root, "handbook.md", "onboarding starts on monday", "ns")

    monkeypatch.setattr(
        embeddings, "embed_query", lambda text: (_ for _ in ()).throw(RuntimeError())
    )
    monkeypatch.setattr(
        bm25, "search", lambda *a, **k: (_ for _ in ()).throw(RuntimeError())
    )

    with pytest.raises(RetrievalError):
        service.search_hybrid("onboarding", "ns", k=4)


def test_results_carry_sqlite_metadata_and_retriever_scores(hybrid):
    service, _, _, _, root = hybrid
    path = root / "handbook.md"
    path.write_text("onboarding starts on monday", encoding="utf-8")
    service.ingest_path(path, "handbook")
    document = service.list_documents()[0]

    hits = service.search_hybrid("onboarding starts on monday", "handbook", k=4)

    hit = hits[0]

    assert hit.doc_id == document.doc_id
    assert hit.title == "handbook"
    assert hit.source.endswith("handbook.md")
    assert hit.namespace == "handbook"
    assert hit.chunk_index == 0
    assert hit.page is None
    assert hit.content == "onboarding starts on monday"
    assert hit.vector_score is not None
    assert hit.bm25_score is not None
    assert hit.score > 0


def test_final_result_count_is_limited(hybrid):
    service, _, _, _, root = hybrid
    for index in range(6):
        _ingest(
            service,
            root,
            f"doc{index}.md",
            f"onboarding note number {index}",
            "ns",
        )

    assert len(service.search_hybrid("onboarding", "ns", k=3)) == 3


def test_hybrid_is_not_filtered_by_min_score(hybrid):
    service, _, _, _, root = hybrid
    _ingest(service, root, "handbook.md", "onboarding starts on monday", "ns")
    service._min_score = 0.99

    # RRF scores are around 1/(60+rank); they must not be dropped as weak hits.
    assert service.search_hybrid("onboarding", "ns", k=4)


def test_blank_query_returns_nothing(hybrid):
    service = hybrid[0]

    assert service.search_hybrid("   ") == []
    assert service.search("   ") == []


def test_unknown_namespace_returns_nothing(hybrid):
    service, _, _, _, root = hybrid
    _ingest(service, root, "handbook.md", "onboarding", "ns")

    assert service.search_hybrid("onboarding", "missing", k=4) == []


def test_empty_knowledge_base_returns_nothing(hybrid):
    service = hybrid[0]

    assert service.search_hybrid("anything") == []


def test_mode_dispatch_uses_the_configured_mode(hybrid):
    service, _, embeddings, _, root = hybrid
    _ingest(service, root, "handbook.md", "onboarding starts on monday", "ns")

    service._search_mode = "bm25"
    embeddings.queries.clear()
    bm25_hits = service.search("onboarding", "ns", k=4)

    assert bm25_hits
    assert embeddings.queries == []

    service._search_mode = "vector"
    embeddings.queries.clear()
    service.search("onboarding", "ns", k=4)

    # Vector dispatch must consult the embedding model; whether the fake
    # embedding clears min_score is not what this test is about.
    assert embeddings.queries == ["onboarding"]


def test_search_bm25_never_calls_the_embedding_model(hybrid):
    service, _, embeddings, _, root = hybrid
    _ingest(service, root, "handbook.md", "onboarding starts on monday", "ns")
    embeddings.queries.clear()

    hits = service.search_bm25("onboarding", "ns", k=4)

    assert hits
    assert embeddings.queries == []


def test_invalid_search_mode_is_rejected(tmp_path):
    connection = create_connection(str(tmp_path / "bad.db"))
    init_schema(connection)

    try:
        with pytest.raises(ValueError, match="search_mode"):
            DocumentService(
                DocumentsRepository(connection),
                VectorIndexStore(tmp_path / "faiss", dimensions=8),
                FakeEmbeddings(),
                chunk_size=100,
                chunk_overlap=0,
                search_mode="magic",
            )
    finally:
        connection.close()


def test_ingestion_refreshes_bm25_results(hybrid):
    service, _, _, _, root = hybrid
    _ingest(service, root, "a.md", "alpha", "ns")
    assert service.search_bm25("zebra", "ns", k=4) == []

    _ingest(service, root, "b.md", "zebra crossing", "ns")

    assert any(
        "zebra" in hit.content
        for hit in service.search_bm25("zebra", "ns", k=4)
    )


def test_reingestion_leaves_no_stale_keyword_matches(hybrid):
    service, _, _, _, root = hybrid
    path = root / "a.md"
    path.write_text("obsolete wording", encoding="utf-8")
    service.ingest_path(path, "ns")
    assert service.search_bm25("obsolete", "ns", k=4)

    path.write_text("replacement wording", encoding="utf-8")
    service.ingest_path(path, "ns")

    assert service.search_bm25("obsolete", "ns", k=4) == []
    assert service.search_bm25("replacement", "ns", k=4)


def test_deletion_removes_hybrid_results(hybrid):
    service, _, _, _, root = hybrid
    _ingest(service, root, "a.md", "alpha only text", "ns")
    document = service.list_documents()[0]

    assert service.delete_document(document.doc_id) is True

    assert service.search_hybrid("alpha", "ns", k=4) == []
    assert service.search_bm25("alpha", "ns", k=4) == []


def test_restart_rebuilds_bm25_from_sqlite(hybrid):
    service, repository, embeddings, _, root = hybrid
    _ingest(service, root, "a.md", "onboarding starts on monday", "ns")

    restarted = DocumentService(
        repository,
        VectorIndexStore(root / "faiss", dimensions=8),
        embeddings,
        chunk_size=200,
        chunk_overlap=0,
        search_mode="hybrid",
    )

    assert restarted.search_bm25("onboarding", "ns", k=4)
    assert restarted.search_hybrid("onboarding", "ns", k=4)


def test_search_documents_tool_runs_hybrid_by_default(hybrid):
    import json

    from agentic_chatbot.tools.documents import create_document_tools

    service, _, embeddings, bm25, root = hybrid
    _ingest(service, root, "handbook.md", "onboarding starts on monday", "ns")
    tools = {tool.name: tool for tool in create_document_tools(service)}
    embeddings.queries.clear()
    bm25.queries.clear()

    payload = json.loads(
        tools["search_documents"].invoke(
            {"query": "onboarding", "namespace": "ns"}
        )
    )

    assert payload["count"] == 1
    result = payload["results"][0]
    assert result["content"] == "onboarding starts on monday"
    assert result["title"] == "handbook"
    assert result["vector_score"] is not None
    assert result["bm25_score"] is not None
    # Hybrid retrieval consulted both retrievers for the same query.
    assert embeddings.queries == ["onboarding"]
    assert bm25.queries == ["onboarding"]


def test_stats_reports_loaded_bm25_indexes(hybrid):
    service, _, _, _, root = hybrid
    _ingest(service, root, "a.md", "alpha", "ns")
    service.search_bm25("alpha", "ns", k=4)

    assert service.stats()["bm25_indexes"] == {"ns": 1}
