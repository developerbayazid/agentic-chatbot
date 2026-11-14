"""Ingestion, dedupe, namespace scoping, and retrieval."""

import pytest

from agentic_chatbot.database import create_connection, init_schema
from agentic_chatbot.loaders import DocumentLoadError, LoadResult, Section
from agentic_chatbot.repository import DocumentsRepository
from agentic_chatbot.services import document_service as document_service_module
from agentic_chatbot.services.document_service import DocumentService
from agentic_chatbot.vector_store import VectorIndexStore
from tests.fakes import FakeEmbeddings


@pytest.fixture
def service_context(tmp_path):
    connection = create_connection(str(tmp_path / "documents.db"))
    init_schema(connection)
    repository = DocumentsRepository(connection)
    store = VectorIndexStore(tmp_path / "faiss", dimensions=8)
    embeddings = FakeEmbeddings(dimensions=8)
    service = DocumentService(
        repository,
        store,
        embeddings,
        chunk_size=100,
        chunk_overlap=10,
        top_k=2,
    )

    try:
        yield service, repository, embeddings, store, tmp_path
    finally:
        connection.close()


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_ingest_file_then_search(service_context):
    service, _, _, _, root = service_context
    path = _write(root / "docs" / "handbook.md", "onboarding starts on monday")

    result = service.ingest_path(path, "handbook")

    assert result.files_indexed == 1
    assert result.files_skipped == 0
    assert result.chunks_created == 1
    assert result.errors == []

    hits = service.search("onboarding starts on monday")

    assert len(hits) == 1
    assert hits[0].title == "handbook"
    assert hits[0].namespace == "handbook"
    assert hits[0].page is None
    assert hits[0].score == pytest.approx(1.0, abs=1e-5)


def test_ingest_directory_skips_unsupported_hidden_and_oversized(service_context):
    service, _, _, _, root = service_context
    service._max_text_bytes = 10
    base = root / "knowledge"
    _write(base / "a.md", "alpha")
    _write(base / "nested" / "b.txt", "beta")
    _write(base / "big.md", "x" * 50)
    _write(base / ".hidden.md", "hidden")
    (base / "image.png").write_bytes(b"binary")

    result = service.ingest_path(base)

    assert result.files_seen == 3
    assert result.files_indexed == 2
    assert len(result.errors) == 1
    assert "big.md" in result.errors[0][0]
    assert service.list_namespaces() == ["default"]


def test_dedupe_skips_unchanged_files_without_embedding(service_context):
    service, _, embeddings, _, root = service_context
    path = _write(root / "docs" / "a.md", "alpha")

    service.ingest_path(path)
    calls_after_first = embeddings.embed_documents_calls
    second = service.ingest_path(path)

    assert second.files_skipped == 1
    assert second.files_indexed == 0
    assert embeddings.embed_documents_calls == calls_after_first


def test_force_reembeds_unchanged_files(service_context):
    service, _, embeddings, _, root = service_context
    path = _write(root / "docs" / "a.md", "alpha")
    service.ingest_path(path)
    calls_after_first = embeddings.embed_documents_calls

    result = service.ingest_path(path, force=True)

    assert result.files_indexed == 1
    assert embeddings.embed_documents_calls > calls_after_first


def test_reingest_after_content_change_replaces_chunks(service_context):
    service, repository, _, _, root = service_context
    path = _write(root / "docs" / "a.md", "alpha")
    service.ingest_path(path)
    document = service.list_documents()[0]
    old_ids = repository.chunk_ids(document.doc_id)

    _write(path, "gamma")
    result = service.ingest_path(path)
    new_ids = repository.chunk_ids(document.doc_id)

    assert result.files_indexed == 1
    assert set(old_ids).isdisjoint(new_ids)
    assert service.search("gamma")
    assert all(hit.content != "alpha" for hit in service.search("alpha"))


def test_search_is_scoped_to_a_namespace(service_context):
    service, _, _, _, root = service_context
    _write(root / "a.md", "alpha")
    _write(root / "b.md", "beta")

    service.ingest_path(root / "a.md", "alpha")
    service.ingest_path(root / "b.md", "beta")

    assert [hit.namespace for hit in service.search("alpha", "alpha")] == ["alpha"]
    assert [hit.namespace for hit in service.search("beta", "beta")] == ["beta"]
    assert service.search("alpha", "beta") == []


def test_search_across_all_namespaces_merges_results(service_context):
    service, _, _, _, root = service_context
    _write(root / "a.md", "shared text")
    _write(root / "b.md", "shared text")

    service.ingest_path(root / "a.md", "alpha")
    service.ingest_path(root / "b.md", "beta")

    hits = service.search("shared text")

    assert {hit.namespace for hit in hits} == {"alpha", "beta"}


def test_missing_path_is_reported_not_raised(service_context):
    service, _, _, _, root = service_context

    result = service.ingest_path(root / "missing")

    assert result.files_seen == 0
    assert result.errors == [(str(root / "missing"), "path not found")]


def test_blank_query_returns_nothing(service_context):
    service = service_context[0]

    assert service.search("   ") == []


def test_k_is_clamped(service_context):
    service, _, _, _, root = service_context
    for index in range(12):
        _write(root / f"doc{index}.md", f"text {index}")
    service.ingest_path(root)

    hits = service.search("text 1", k=99)

    assert 0 < len(hits) <= 10


def test_unsupported_file_raises(service_context):
    service, _, _, _, root = service_context
    path = root / "image.png"
    path.write_bytes(b"binary")

    with pytest.raises(DocumentLoadError, match="unsupported"):
        service.ingest_file(path, "default")


def test_unreadable_pdf_is_recorded_and_others_still_index(service_context):
    service, _, _, _, root = service_context
    _write(root / "good.md", "alpha")
    (root / "broken.pdf").write_bytes(b"%PDF-but-not-really")

    result = service.ingest_path(root)

    assert result.files_indexed == 1
    assert len(result.errors) == 1
    assert "broken.pdf" in result.errors[0][0]


def test_pdf_pages_are_preserved_and_truncation_warned(
    service_context, monkeypatch
):
    service, _, _, _, root = service_context
    path = root / "policy.pdf"
    path.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(
        document_service_module,
        "load_file",
        lambda path, max_pdf_pages: LoadResult(
            sections=[Section(page=3, text="policy body")],
            truncated=True,
        ),
    )

    result = service.ingest_path(path, "policies")
    hits = service.search("policy body", "policies")

    assert result.warnings == [f"{hits[0].source}: truncated to 200 pages"]
    assert hits[0].page == 3


def test_index_write_failure_compensates_the_sql_insert(service_context):
    service, repository, _, _, root = service_context
    path = _write(root / "docs" / "a.md", "alpha")

    class BrokenStore:
        def replace(self, *args, **kwargs):
            raise RuntimeError("index write failed")

    service._vector_store = BrokenStore()

    result = service.ingest_path(path)

    assert result.files_indexed == 0
    assert result.errors[0][1] == "index write failed"
    assert repository.find_by_source("default", service._source(path)) is None


def test_delete_document_removes_vectors(service_context):
    service, _, _, store, root = service_context
    path = _write(root / "docs" / "a.md", "alpha")
    service.ingest_path(path)
    document = service.list_documents()[0]

    assert service.delete_document(document.doc_id) is True
    assert service.search("alpha") == []
    assert store.search(["default"], [0.0] * 8, k=5) == []
    assert service.delete_document(document.doc_id) is False


def test_stats_merges_database_and_index_counts(service_context):
    service, _, _, _, root = service_context
    _write(root / "a.md", "alpha")
    service.ingest_path(root)

    stats = service.stats()

    assert stats["documents"] == 1
    assert stats["chunks"] == 1
    assert stats["namespaces"] == 1
    assert stats["indexes"] == {"default": 1}
