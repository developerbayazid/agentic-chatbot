"""SQL behaviour for documents and their chunks."""

import pytest

from agentic_chatbot.database import create_connection, init_schema
from agentic_chatbot.models import Chunk
from agentic_chatbot.repository import DocumentsRepository


@pytest.fixture
def repository(tmp_path):
    connection = create_connection(str(tmp_path / "documents.db"))
    init_schema(connection)
    repository = DocumentsRepository(connection)

    try:
        yield repository
    finally:
        connection.close()


def test_replace_document_inserts_document_and_chunks(repository):
    document, row_ids = repository.replace_document(
        "handbook",
        "docs/handbook.md",
        "handbook",
        "hash-1",
        42,
        [Chunk(content="first"), Chunk(content="second")],
    )

    assert document.namespace == "handbook"
    assert document.source == "docs/handbook.md"
    assert document.title == "handbook"
    assert document.content_hash == "hash-1"
    assert document.size_bytes == 42
    assert len(row_ids) == 2
    assert repository.chunk_ids(document.doc_id) == row_ids


def test_replace_document_updates_in_place_and_drops_old_chunks(repository):
    first, first_ids = repository.replace_document(
        "handbook", "docs/a.md", "a", "hash-1", 10, [Chunk("one"), Chunk("two")]
    )
    second, second_ids = repository.replace_document(
        "handbook", "docs/a.md", "a", "hash-2", 11, [Chunk("three")]
    )

    assert second.doc_id == first.doc_id
    assert second.content_hash == "hash-2"
    assert second.size_bytes == 11
    assert repository.chunk_ids(first.doc_id) == second_ids
    assert set(first_ids).isdisjoint(second_ids)


def test_page_metadata_round_trips(repository):
    document, row_ids = repository.replace_document(
        "policies",
        "docs/policy.pdf",
        "policy",
        "hash",
        10,
        [Chunk(content="page two", page=2), Chunk(content="plain")],
    )

    rows = repository.chunks_by_ids(row_ids)

    assert rows[row_ids[0]]["page"] == 2
    assert rows[row_ids[1]]["page"] is None
    assert rows[row_ids[0]]["title"] == "policy"
    assert rows[row_ids[0]]["source"] == "docs/policy.pdf"
    assert rows[row_ids[0]]["content"] == "page two"


def test_chunks_by_ids_is_empty_for_no_ids(repository):
    assert repository.chunks_by_ids([]) == {}


def test_delete_document_removes_chunks(repository):
    document, _ = repository.replace_document(
        "default", "docs/a.md", "a", "hash", 1, [Chunk("text")]
    )

    assert repository.delete_document(document.doc_id) is True
    assert repository.get(document.doc_id) is None
    assert repository.chunk_ids(document.doc_id) == []
    assert repository.delete_document(document.doc_id) is False


def test_list_documents_and_namespaces(repository):
    repository.replace_document(
        "beta", "docs/b.md", "b", "h1", 1, [Chunk("b")]
    )
    repository.replace_document(
        "alpha", "docs/a.md", "a", "h2", 1, [Chunk("a")]
    )

    assert repository.list_namespaces() == ["alpha", "beta"]
    assert [item.namespace for item in repository.list_documents()] == [
        "alpha",
        "beta",
    ]
    assert [item.source for item in repository.list_documents("beta")] == [
        "docs/b.md"
    ]


def test_stats(repository):
    repository.replace_document(
        "alpha", "docs/a.md", "a", "h", 1, [Chunk("one"), Chunk("two")]
    )

    assert repository.stats() == {
        "documents": 1,
        "chunks": 2,
        "namespaces": 1,
    }


def test_list_chunks_returns_namespace_content_in_id_order(repository):
    _, alpha_ids = repository.replace_document(
        "alpha", "docs/a.md", "a", "h", 1, [Chunk("first"), Chunk("second")]
    )
    repository.replace_document(
        "beta", "docs/b.md", "b", "h", 1, [Chunk("elsewhere")]
    )

    assert repository.list_chunks("alpha") == [
        (alpha_ids[0], "first"),
        (alpha_ids[1], "second"),
    ]
    assert repository.list_chunks("missing") == []


def test_chunks_fingerprint_tracks_inserts_and_deletes(repository):
    empty = repository.chunks_fingerprint("alpha")
    document, alpha_ids = repository.replace_document(
        "alpha", "docs/a.md", "a", "h", 1, [Chunk("one"), Chunk("two")]
    )
    populated = repository.chunks_fingerprint("alpha")

    assert empty == (0, 0, 0)
    assert populated == (2, alpha_ids[-1], sum(alpha_ids))

    repository.delete_document(document.doc_id)

    assert repository.chunks_fingerprint("alpha") == (0, 0, 0)


def test_chunks_fingerprint_changes_fingerprint_on_reingest(repository):
    repository.replace_document(
        "alpha", "docs/a.md", "a", "h1", 1, [Chunk("one")]
    )
    before = repository.chunks_fingerprint("alpha")

    repository.replace_document(
        "alpha", "docs/a.md", "a", "h2", 1, [Chunk("one")]
    )

    assert repository.chunks_fingerprint("alpha") != before


def test_init_schema_is_idempotent(tmp_path):
    path = tmp_path / "twice.db"

    first = create_connection(str(path))
    init_schema(first)
    first.close()

    second = create_connection(str(path))
    init_schema(second)
    tables = {
        row[0]
        for row in second.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    second.close()

    assert {"documents", "document_chunks", "rag_meta"} <= tables


def test_changing_embedding_dimensions_raises(tmp_path):
    path = tmp_path / "dimensions.db"

    connection = create_connection(str(path))
    init_schema(connection, embedding_dimensions=8)

    with pytest.raises(RuntimeError, match="dimension"):
        init_schema(connection, embedding_dimensions=16)

    connection.close()
