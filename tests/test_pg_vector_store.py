"""Embedding storage in PostgreSQL: parity with FAISS, and the security property.

These run against a real server (``TEST_POSTGRES_DSN``) and assert the two things
that matter: scores mean the same as they did under FAISS (cosine similarity over
normalised vectors), and an owner's search cannot see or be reordered by another
owner's chunks.
"""

from __future__ import annotations

import math
import os
import shutil
from pathlib import Path

import pytest

from agentic_chatbot.models import Chunk

POSTGRES_DSN = os.environ.get("TEST_POSTGRES_DSN", "")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN, reason="TEST_POSTGRES_DSN is not set"
)

REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_DATASET = (
    REPO_ROOT / "inventory-data" / "inventory" / "inventory_data.seed.json"
)

DIMENSIONS = 4


def _fresh():
    from agentic_chatbot.pg_vector_store import PgVectorStore
    from agentic_chatbot.postgres import create_connection, init_schema
    from agentic_chatbot.repository import DocumentsRepository

    connection = create_connection(POSTGRES_DSN)

    # Reset first, schema second. `init_schema` refuses to run when a stored
    # `embedding_dimensions` disagrees with the requested size, and another test
    # file may legitimately have run with 1536. The stale row and any wrong-sized
    # `embedding_vec` column must go before the schema is applied.
    _reset_dimension_artifacts(connection)

    init_schema(connection, embedding_dimensions=DIMENSIONS)

    with connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE document_chunks, documents, notes, threads RESTART IDENTITY"
        )
    connection.commit()

    return connection, DocumentsRepository(connection), PgVectorStore(
        connection, DIMENSIONS
    )


def _reset_dimension_artifacts(connection) -> None:
    """Drop the pgvector column so its fixed dimension does not leak.

    ``embedding_vec`` is created as ``vector(N)`` for whatever N the current test
    configured. A ``vector(4)`` left behind makes every later 1536-dimension test
    fail with "expected 4 dimensions, not 1536". Dropping it (and its index) lets
    the next ``init_schema`` recreate it at the right size.

    Safe on an empty database: every statement is a no-op when the object is
    absent, which is why the calls are guarded by ``IF EXISTS``.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('document_chunks') AS found")
        if cursor.fetchone()["found"] is not None:
            cursor.execute("DROP INDEX IF EXISTS idx_chunks_embedding_hnsw")
            cursor.execute(
                "ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding_vec"
            )

        cursor.execute("SELECT to_regclass('rag_meta') AS found")
        if cursor.fetchone()["found"] is not None:
            cursor.execute(
                "DELETE FROM rag_meta WHERE key = 'embedding_dimensions'"
            )
    connection.commit()


@pytest.fixture
def pg():
    connection, documents, vectors = _fresh()

    try:
        yield documents, vectors
    finally:
        # Leave the database usable: these tests run with a 4-dimension config,
        # and both the stored dimension row and the vector column are sized.
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "TRUNCATE document_chunks, documents, notes, threads "
                    "RESTART IDENTITY"
                )
            connection.commit()
            _reset_dimension_artifacts(connection)
        finally:
            connection.close()


@requires_postgres
def test_uses_pgvector_when_the_extension_is_installed(pg):
    """Assert the fast path is really in use, not silently falling back.

    Without this, a missing extension would degrade search to a full scan and
    every other test here would still pass.
    """
    documents, vectors = pg
    connection = vectors._connection

    installed = connection.cursor().execute(
        "SELECT 1 AS present FROM pg_extension WHERE extname = 'vector'"
    ).fetchone()

    if installed is None:
        pytest.skip("pgvector is not installed in this database")

    assert vectors.mode == "pgvector"

    # The column and the HNSW index must both exist.
    columns = connection.cursor().execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'document_chunks' AND column_name = 'embedding_vec'"
    ).fetchall()
    assert columns, "embedding_vec column is missing"

    indexes = connection.cursor().execute(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'idx_chunks_embedding_hnsw'"
    ).fetchall()
    assert indexes, "HNSW index is missing"
    assert "hnsw" in indexes[0]["indexdef"].lower()


@requires_postgres
def test_vectors_round_trip_and_rank_by_cosine(pg):
    documents, vectors = pg

    document, row_ids = documents.replace_document(
        "default", "a.txt", "A", "h", 1, [Chunk("one"), Chunk("two")]
    )

    # "two" is closer to the query than "one".
    vectors.add(
        "default",
        row_ids,
        [[1.0, 0.0, 0.0, 0.0], [0.9, 0.1, 0.0, 0.0]],
    )

    results = vectors.search(["default"], [1.0, 0.0, 0.0, 0.0], 2)

    assert [row_id for row_id, _ in results] == [row_ids[0], row_ids[1]]
    # A normalised identical vector scores exactly 1.0, as FAISS's inner product did.
    assert results[0][1] == pytest.approx(1.0, abs=1e-9)
    assert results[1][1] < results[0][1]


@requires_postgres
def test_scores_match_cosine_similarity(pg):
    documents, vectors = pg
    _, row_ids = documents.replace_document(
        "default", "a.txt", "A", "h", 1, [Chunk("x")]
    )

    stored = [3.0, 4.0, 0.0, 0.0]  # normalises to [0.6, 0.8, 0, 0]
    vectors.add("default", row_ids, [stored])

    query = [1.0, 0.0, 0.0, 0.0]
    (_, score), = vectors.search(["default"], query, 1)

    # cos = (1*0.6) / (1 * 1) = 0.6
    # pgvector stores float32, so exact double equality does not hold; the
    # tolerance reflects single precision rather than a wrong result.
    assert score == pytest.approx(0.6, abs=1e-6)


@requires_postgres
def test_stats_and_namespace_filtering(pg):
    documents, vectors = pg

    _, alpha_ids = documents.replace_document(
        "alpha", "a.txt", "A", "h", 1, [Chunk("x"), Chunk("y")]
    )
    _, beta_ids = documents.replace_document(
        "beta", "b.txt", "B", "h", 1, [Chunk("z")]
    )

    vectors.add("alpha", alpha_ids, [[1, 0, 0, 0], [0, 1, 0, 0]])
    vectors.add("beta", beta_ids, [[1, 0, 0, 0]])

    assert vectors.stats() == {"alpha": 2, "beta": 1}

    only_beta = vectors.search(["beta"], [1, 0, 0, 0], 10)
    assert [row_id for row_id, _ in only_beta] == beta_ids

    both = vectors.search(["alpha", "beta"], [1, 0, 0, 0], 10)
    assert len(both) == 3


@requires_postgres
def test_rows_without_vectors_are_skipped(pg):
    documents, vectors = pg
    _, row_ids = documents.replace_document(
        "default", "a.txt", "A", "h", 1, [Chunk("one"), Chunk("two")]
    )

    vectors.add("default", [row_ids[0]], [[1, 0, 0, 0]])

    results = vectors.search(["default"], [1, 0, 0, 0], 10)

    # The chunk with no vector at all must not appear as a zero score.
    assert [row_id for row_id, _ in results] == [row_ids[0]]


@requires_postgres
def test_remove_clears_vectors(pg):
    documents, vectors = pg
    _, row_ids = documents.replace_document(
        "default", "a.txt", "A", "h", 1, [Chunk("x")]
    )
    vectors.add("default", row_ids, [[1, 0, 0, 0]])

    vectors.remove("default", row_ids)

    assert vectors.search(["default"], [1, 0, 0, 0], 10) == []
    assert vectors.stats() == {}


@requires_postgres
def test_wrong_dimension_is_rejected(pg):
    _, vectors = pg

    with pytest.raises(ValueError):
        vectors.add("default", [1], [[1.0, 0.0]])  # 2 != DIMENSIONS


@requires_postgres
def test_owner_isolation_end_to_end(pg, tmp_path):
    """Alice's search must never return, or be reordered by, Bob's chunk.

    This drives ``DocumentService`` itself, so the filter-before-fusion property
    is exercised on the Postgres vector path rather than only in the repository.
    """
    from agentic_chatbot.container import ChatbotContainer
    from agentic_chatbot.config import Settings
    from tests.fakes import FakeEmbeddings

    inventory_copy = tmp_path / "inventory" / "inventory_data.json"
    inventory_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INVENTORY_DATASET, inventory_copy)

    settings = Settings(
        database_backend="postgres",
        postgres_dsn=POSTGRES_DSN,
        rag_index_path=str(tmp_path / "faiss"),
        inventory_data_path=str(inventory_copy),
        embedding_dimensions=DIMENSIONS,
        openai_api_key="test-key",
        _env_file=None,
    )

    container = ChatbotContainer(settings)
    container.document_service._embeddings = FakeEmbeddings(dimensions=DIMENSIONS)

    try:
        alice = tmp_path / "alice.txt"
        alice.write_text("Alice private salary review", encoding="utf-8")
        bob = tmp_path / "bob.txt"
        bob.write_text("Bob private salary review", encoding="utf-8")

        container.document_service.ingest_file(
            alice, namespace="default", owner_id="alice"
        )
        container.document_service.ingest_file(
            bob, namespace="default", owner_id="bob"
        )

        alice_hits = container.document_service.search(
            "salary review", owner_id="alice"
        )
        bob_hits = container.document_service.search("salary review", owner_id="bob")

        assert alice_hits and bob_hits
        assert all("Alice" in hit.content for hit in alice_hits)
        assert all("Bob" in hit.content for hit in bob_hits)
        assert not any("Bob" in hit.content for hit in alice_hits)
        assert not any("Alice" in hit.content for hit in bob_hits)
    finally:
        container.close()
        # Reset the dimension row and vector column so later tests are not blocked
        # by this file's small embedding size.
        from agentic_chatbot.postgres import create_connection

        cleanup = create_connection(POSTGRES_DSN)
        with cleanup.cursor() as cursor:
            cursor.execute(
                "TRUNCATE document_chunks, documents, notes, threads RESTART IDENTITY"
            )
        cleanup.commit()
        _reset_dimension_artifacts(cleanup)
        cleanup.close()
