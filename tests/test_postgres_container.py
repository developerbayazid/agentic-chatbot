"""Acceptance: the real services work against PostgreSQL, not just the repos.

Builds an actual ``ChatbotContainer`` on Postgres and drives ``ThreadService``,
``NotesRepository`` and ``DocumentService`` through it — the same code paths the
CLI and the API use. Embeddings are a deterministic double so no network is
needed, but the checkpointer is the real ``PostgresSaver``.

Skipped unless ``TEST_POSTGRES_DSN`` is set.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

POSTGRES_DSN = os.environ.get("TEST_POSTGRES_DSN", "")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN, reason="TEST_POSTGRES_DSN is not set"
)

REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_DATASET = (
    REPO_ROOT / "inventory-data" / "inventory" / "inventory_data.seed.json"
)


def _truncate(dsn: str) -> None:
    """Empty every application table so assertions on counts are meaningful.

    The dimension row is cleared too: another test file may have run with a
    different embedding size, and the guard would otherwise refuse to start.
    """
    from agentic_chatbot.postgres import create_connection, init_schema

    connection = create_connection(dsn)

    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('rag_meta') AS found")
        has_schema = cursor.fetchone()["found"] is not None

        if has_schema:
            cursor.execute("DELETE FROM rag_meta WHERE key = 'embedding_dimensions'")

            # Drop any pgvector column left at another test file's dimension, so
            # `init_schema` recreates it at this suite's size.
            cursor.execute(
                "ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding_vec"
            )
    connection.commit()

    init_schema(connection)

    with connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE document_chunks, documents, notes, threads RESTART IDENTITY"
        )
        # Checkpoint tables are managed by LangGraph; clear them too so a rerun
        # starts from a known state.
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            if _exists(cursor, table):
                cursor.execute(f"TRUNCATE {table}")

    connection.commit()
    connection.close()


def _exists(cursor, table: str) -> bool:
    cursor.execute("SELECT to_regclass(%s) AS found", (table,))
    return cursor.fetchone()["found"] is not None


@pytest.fixture
def pg_container(tmp_path):
    from agentic_chatbot.config import Settings
    from agentic_chatbot.container import ChatbotContainer

    inventory_copy = tmp_path / "inventory" / "inventory_data.json"
    inventory_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INVENTORY_DATASET, inventory_copy)

    _truncate(POSTGRES_DSN)

    settings = Settings(
        database_backend="postgres",
        postgres_dsn=POSTGRES_DSN,
        rag_index_path=str(tmp_path / "faiss"),
        inventory_data_path=str(inventory_copy),
        openai_api_key="test-key",
        _env_file=None,
    )

    container = ChatbotContainer(settings)

    from tests.fakes import FakeEmbeddings

    container.document_service._embeddings = FakeEmbeddings(
        dimensions=settings.embedding_dimensions
    )

    try:
        yield container
    finally:
        container.close()


@requires_postgres
def test_container_uses_the_postgres_checkpointer(pg_container):
    from langgraph.checkpoint.postgres import PostgresSaver

    assert isinstance(pg_container.checkpointer, PostgresSaver)


@requires_postgres
def test_thread_service_round_trip(pg_container):
    threads = pg_container.thread_service

    created = threads.create_thread("Postgres thread", owner_id="alice")
    assert threads.thread_exists(created.thread_id)

    threads.rename_thread(created.thread_id, "Renamed")
    assert threads.get_thread(created.thread_id).title == "Renamed"

    assert [t.thread_id for t in threads.list_threads(owner_id="alice")] == [
        created.thread_id
    ]

    assert threads.delete_thread(created.thread_id) is True
    assert threads.thread_exists(created.thread_id) is False


@requires_postgres
def test_document_ingest_and_search_on_postgres(pg_container, tmp_path):
    """The full RAG path: read, chunk, embed, store in Postgres, then retrieve."""
    document = tmp_path / "handbook.txt"
    document.write_text(
        "The BAYAZID handbook says expense claims are due within 30 days.\n\n"
        "The onboarding guide describes laptop setup and account access.",
        encoding="utf-8",
    )

    chunks, skipped, warning = pg_container.document_service.ingest_file(
        document, namespace="default"
    )

    assert skipped is False
    assert warning is None
    assert chunks > 0

    hits = pg_container.document_service.search("How long do expense claims take?")

    assert hits, "expected at least one chunk back from Postgres-backed search"
    assert any("30 days" in hit.content for hit in hits)


@requires_postgres
def test_owner_isolation_holds_on_postgres(pg_container, tmp_path):
    """The critical security property, re-proven on the new backend."""
    service = pg_container.document_service

    alice_file = tmp_path / "alice.txt"
    alice_file.write_text("Alice's private salary review notes.", encoding="utf-8")
    bob_file = tmp_path / "bob.txt"
    bob_file.write_text("Bob's private salary review notes.", encoding="utf-8")

    service.ingest_file(alice_file, namespace="default", owner_id="alice")
    service.ingest_file(bob_file, namespace="default", owner_id="bob")

    alice = service.search("salary review", owner_id="alice")
    bob = service.search("salary review", owner_id="bob")

    assert alice and bob
    assert all("Alice" in hit.content for hit in alice)
    assert all("Bob" in hit.content for hit in bob)
    # Alice must never see Bob's chunk, and vice versa.
    assert not any("Bob" in hit.content for hit in alice)
    assert not any("Alice" in hit.content for hit in bob)


@requires_postgres
def test_stats_reflect_postgres_rows(pg_container, tmp_path):
    document = tmp_path / "invoices.txt"
    document.write_text("One document about invoices.", encoding="utf-8")
    pg_container.document_service.ingest_file(document, namespace="default")

    stats = pg_container.documents_repository.stats()

    assert stats["documents"] == 1
    assert stats["chunks"] >= 1
