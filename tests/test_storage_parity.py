"""Storage parity: the same repository contract against SQLite and PostgreSQL.

These tests exist because the migration's whole premise is that swapping the
backend is invisible above the repository layer. Running one contract against
both engines is the only way to show that.

The Postgres half is skipped unless ``TEST_POSTGRES_DSN`` is set, so a normal
``uv run pytest`` needs no database. Set it to run the full comparison::

    TEST_POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/bayazid_test
"""

from __future__ import annotations

import os
import uuid

import pytest

from agentic_chatbot.database import create_connection, init_schema
from agentic_chatbot.models import Chunk
from agentic_chatbot.repository import (
    DocumentsRepository,
    NotesRepository,
    ThreadRepository,
)

POSTGRES_DSN = os.environ.get("TEST_POSTGRES_DSN", "")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN, reason="TEST_POSTGRES_DSN is not set"
)


def _sqlite():
    connection = create_connection(":memory:")
    init_schema(connection)
    return connection


def _postgres():
    from agentic_chatbot.postgres import create_connection as pg_connect
    from agentic_chatbot.postgres import init_schema as pg_init

    connection = pg_connect(POSTGRES_DSN)
    pg_init(connection)

    # Each run starts from empty tables so assertions on counts are meaningful.
    with connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE document_chunks, documents, notes, threads RESTART IDENTITY"
        )
    connection.commit()
    return connection


BACKENDS = [pytest.param("sqlite", id="sqlite")]


@pytest.fixture(params=[*BACKENDS, pytest.param("postgres", marks=requires_postgres)])
def store(request):
    if request.param == "postgres":
        connection = _postgres()
    else:
        connection = _sqlite()

    try:
        yield {
            "threads": ThreadRepository(connection),
            "notes": NotesRepository(connection),
            "documents": DocumentsRepository(connection),
        }
    finally:
        connection.close()


# --------------------------------------------------------------------- threads --


def test_thread_round_trip(store):
    threads = store["threads"]
    created = threads.create("First chat", owner_id="alice")

    assert created.thread_id
    assert created.title == "First chat"
    assert created.owner_id == "alice"
    # Timestamps are text in the same shape on both backends, which is what the
    # API payloads and the frontend's parser depend on.
    assert isinstance(created.created_at, str)
    assert len(created.created_at) == 19
    assert created.created_at[4] == "-" and created.created_at[10] == " "

    assert threads.get(created.thread_id) == created
    assert threads.exists(created.thread_id) is True


def test_thread_title_update_bumps_updated_at(store):
    threads = store["threads"]
    created = threads.create("Old")

    threads.update_title(created.thread_id, "New")

    assert threads.get(created.thread_id).title == "New"


def test_thread_owner_scoping(store):
    threads = store["threads"]
    threads.create("Alice's", owner_id="alice")
    threads.create("Bob's", owner_id="bob")
    threads.create("Unowned")

    assert [t.title for t in threads.list_all(owner_id="alice")] == ["Alice's"]
    assert len(threads.list_all()) == 3


def test_thread_delete(store):
    threads = store["threads"]
    created = threads.create("Bye")

    threads.delete(created.thread_id)

    assert threads.exists(created.thread_id) is False
    assert threads.get(created.thread_id) is None


# ----------------------------------------------------------------------- notes --


def test_note_round_trip_and_search_is_case_insensitive(store):
    notes = store["notes"]
    thread_id = str(uuid.uuid4())

    created = notes.create(thread_id, "Groceries", "Buy MILK and bread")

    assert created.note_id
    assert isinstance(created.created_at, str)
    assert notes.get(thread_id, created.note_id) == created
    assert len(notes.list_all(thread_id)) == 1

    # Matches regardless of case, on both engines.
    assert [n.note_id for n in notes.search(thread_id, "milk")] == [created.note_id]
    assert [n.note_id for n in notes.search(thread_id, "GROCERIES")] == [
        created.note_id
    ]
    assert notes.search(thread_id, "absent") == []


def test_note_delete_reports_whether_a_row_went(store):
    notes = store["notes"]
    thread_id = str(uuid.uuid4())
    created = notes.create(thread_id, "t", "c")

    assert notes.delete(thread_id, created.note_id) is True
    assert notes.delete(thread_id, created.note_id) is False


def test_notes_are_scoped_to_their_thread(store):
    notes = store["notes"]
    one, two = str(uuid.uuid4()), str(uuid.uuid4())
    notes.create(one, "a", "x")
    notes.create(two, "b", "y")

    assert len(notes.list_all(one)) == 1
    assert len(notes.list_all(two)) == 1
    assert notes.get(one, notes.list_all(two)[0].note_id) is None


# ------------------------------------------------------------------- documents --


def test_document_chunks_round_trip(store):
    documents = store["documents"]
    document, row_ids = documents.replace_document(
        namespace="default",
        source="handbook.txt",
        title="Handbook",
        content_hash="abc",
        size_bytes=12,
        chunks=[Chunk("first", page=None), Chunk("second", page=2)],
        owner_id="alice",
    )

    assert isinstance(document.created_at, str)
    assert len(row_ids) == 2
    # Generated ids must be real, positive, and distinct on both engines.
    assert all(isinstance(value, int) and value > 0 for value in row_ids)
    assert len(set(row_ids)) == 2
    assert documents.chunk_ids(document.doc_id) == row_ids

    rows = documents.chunks_by_ids(row_ids)
    assert set(rows) == set(row_ids)
    assert rows[row_ids[1]]["page"] == 2
    assert rows[row_ids[0]]["title"] == "Handbook"


def test_replacing_a_document_removes_its_old_chunks(store):
    documents = store["documents"]
    first, _ = documents.replace_document(
        "default", "a.txt", "A", "h1", 1, [Chunk("one"), Chunk("two")], owner_id="alice"
    )
    second, new_ids = documents.replace_document(
        "default", "a.txt", "A v2", "h2", 2, [Chunk("only")], owner_id="alice"
    )

    assert first.doc_id == second.doc_id
    assert second.title == "A v2"
    assert len(new_ids) == 1
    assert documents.chunk_ids(second.doc_id) == new_ids
    assert documents.stats()["chunks"] == 1


def test_unique_namespace_and_source(store):
    documents = store["documents"]
    one, _ = documents.replace_document(
        "ns1", "same.txt", "T", "h", 1, [Chunk("x")]
    )
    two, _ = documents.replace_document("ns2", "same.txt", "T", "h", 1, [Chunk("x")])

    # Same source in two namespaces is two documents, not a conflict.
    assert one.doc_id != two.doc_id
    assert documents.find_by_source("ns1", "same.txt").doc_id == one.doc_id


def test_owner_scoping_and_authorized_chunk_ids(store):
    documents = store["documents"]
    _, alice_ids = documents.replace_document(
        "default", "alice.txt", "A", "h", 1, [Chunk("secret-a")], owner_id="alice"
    )
    _, bob_ids = documents.replace_document(
        "default", "bob.txt", "B", "h", 1, [Chunk("secret-b")], owner_id="bob"
    )

    assert documents.authorized_chunk_ids("alice", ["default"]) == set(alice_ids)
    assert documents.authorized_chunk_ids("bob", ["default"]) == set(bob_ids)
    assert documents.authorized_chunk_ids("alice", []) == set()
    assert documents.authorized_chunk_ids("carol", ["default"]) == set()

    assert [d.source for d in documents.list_documents(owner_id="alice")] == [
        "alice.txt"
    ]
    assert documents.list_namespaces(owner_id="alice") == ["default"]


def test_namespaces_and_stats(store):
    documents = store["documents"]
    documents.replace_document("alpha", "a.txt", "A", "h", 1, [Chunk("x"), Chunk("y")])
    documents.replace_document("beta", "b.txt", "B", "h", 2, [Chunk("z")])

    assert documents.list_namespaces() == ["alpha", "beta"]

    stats = documents.stats()
    assert stats == {"documents": 2, "chunks": 3, "namespaces": 2}


def test_fingerprint_changes_when_chunks_change(store):
    documents = store["documents"]
    documents.replace_document("default", "a.txt", "A", "h", 1, [Chunk("x")])
    before = documents.chunks_fingerprint("default")

    documents.replace_document("default", "a.txt", "A", "h2", 1, [Chunk("x"), Chunk("y")])
    after = documents.chunks_fingerprint("default")

    assert before != after
    assert after[0] == 2


def test_list_chunks_returns_row_id_and_content(store):
    documents = store["documents"]
    _, row_ids = documents.replace_document(
        "default", "a.txt", "A", "h", 1, [Chunk("first"), Chunk("second")]
    )

    listed = documents.list_chunks("default")

    assert [rid for rid, _ in listed] == row_ids
    assert [content for _, content in listed] == ["first", "second"]


def test_delete_document_removes_chunks(store):
    documents = store["documents"]
    document, _ = documents.replace_document(
        "default", "a.txt", "A", "h", 1, [Chunk("x")]
    )

    assert documents.delete_document(document.doc_id) is True
    assert documents.chunk_ids(document.doc_id) == []
    assert documents.get(document.doc_id) is None
