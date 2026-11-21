"""Persistence: owner columns and shared-connection locking."""

import threading

import psycopg
import pytest

from agentic_chatbot.container import ChatbotContainer
from agentic_chatbot.models import Chunk
from agentic_chatbot.postgres import connection_lock
from agentic_chatbot.repository import (
    DocumentsRepository,
    NotesRepository,
    ThreadRepository,
)
from tests.pg import connect


def _columns(connection, schema, table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s",
            (schema, table),
        )
        return {row["column_name"] for row in cursor.fetchall()}


def test_schema_has_owner_columns(container, schema):
    assert "owner_id" in _columns(container.connection, schema, "threads")
    assert "owner_id" in _columns(container.connection, schema, "documents")


def test_connection_lock_is_shared_per_connection(schema):
    first = connect(schema)
    second = connect(schema)

    try:
        assert connection_lock(first) is connection_lock(first)
        assert connection_lock(first) is not connection_lock(second)
        assert isinstance(connection_lock(first), type(threading.RLock()))
    finally:
        first.close()
        second.close()


def test_repositories_share_the_connection_lock(container):
    lock = connection_lock(container.connection)

    assert container.thread_repository._lock is lock
    assert container.documents_repository._lock is lock
    assert container.notes_repository._lock is lock


@pytest.mark.parametrize("title", ["alpha", "beta"])
def test_owner_scoped_threads(container, title):
    mine = container.thread_service.create_thread(title, owner_id="alice")
    container.thread_service.create_thread("other", owner_id="bob")

    listed = container.thread_service.list_threads(owner_id="alice")

    assert [thread.thread_id for thread in listed] == [mine.thread_id]
    assert mine.owner_id == "alice"
    assert len(container.thread_service.list_threads()) == 2


def test_unowned_threads_stay_visible_to_the_cli(container):
    container.thread_service.create_thread("cli chat", owner_id=None)
    container.thread_service.create_thread("api chat", owner_id="alice")

    assert len(container.thread_service.list_threads()) == 2
    assert len(container.thread_service.list_threads(owner_id="alice")) == 1


def test_documents_are_owner_scoped(connection):
    repository = DocumentsRepository(connection)

    alice, _ = repository.replace_document(
        "u_alice",
        "a.md",
        "Alice",
        "hash-a",
        10,
        [Chunk(content="alpha only")],
        owner_id="alice",
    )
    bob, _ = repository.replace_document(
        "u_bob",
        "b.md",
        "Bob",
        "hash-b",
        10,
        [Chunk(content="beta only")],
        owner_id="bob",
    )

    assert [d.doc_id for d in repository.list_documents(owner_id="alice")] == [
        alice.doc_id
    ]
    assert [d.doc_id for d in repository.list_documents(owner_id="bob")] == [
        bob.doc_id
    ]
    assert len(repository.list_documents()) == 2
    assert repository.list_namespaces(owner_id="alice") == ["u_alice"]
    assert "u_bob" not in repository.list_namespaces(owner_id="alice")


def test_authorized_chunk_ids_are_owner_scoped(connection):
    repository = DocumentsRepository(connection)

    alice, alice_ids = repository.replace_document(
        "shared",
        "a.md",
        "Alice",
        "hash-a",
        10,
        [Chunk(content="alpha"), Chunk(content="alpha two")],
        owner_id="alice",
    )
    bob, bob_ids = repository.replace_document(
        "shared",
        "b.md",
        "Bob",
        "hash-b",
        10,
        [Chunk(content="beta")],
        owner_id="bob",
    )

    authorized = repository.authorized_chunk_ids("alice", ["shared"])

    assert authorized == set(alice_ids)
    assert authorized.isdisjoint(bob_ids)
    assert repository.authorized_chunk_ids("alice", []) == set()
    assert repository.authorized_chunk_ids("nobody", ["shared"]) == set()
    assert repository.authorized_chunk_ids("alice", ["missing"]) == set()


def test_concurrent_writes_on_one_connection_are_serialized(container):
    """Interleaved writes through multiple repositories must not corrupt SQL.

    Without a shared lock, one thread's commit can commit another thread's
    half-built transaction. This exercises that path directly.
    """
    errors: list[BaseException] = []
    created: list[str] = []
    barrier = threading.Barrier(8)

    def worker(index: int) -> None:
        repository = ThreadRepository(container.connection)
        notes = NotesRepository(container.connection)
        documents = DocumentsRepository(container.connection)

        try:
            barrier.wait(timeout=10)

            for round_index in range(5):
                thread = repository.create(f"w{index}-{round_index}")
                created.append(thread.thread_id)
                notes.create(thread.thread_id, "note", "body")

                document, row_ids = documents.replace_document(
                    "concurrent",
                    f"w{index}-{round_index}.md",
                    "title",
                    f"hash-{index}-{round_index}",
                    3,
                    [Chunk(content="body")],
                    owner_id=f"user-{index}",
                )
                assert len(row_ids) == 1
                assert documents.get(document.doc_id) is not None
        except BaseException as error:  # noqa: BLE001 - collected for the assert
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors[:3]
    assert len(created) == 40
    assert len(set(created)) == 40
    assert len(container.thread_service.list_threads()) == 40
    assert container.documents_repository.stats()["documents"] == 40
    assert container.documents_repository.stats()["chunks"] == 40


def test_per_thread_locks_are_isolated(container):
    first = container.thread_lock("thread-a")
    second = container.thread_lock("thread-b")

    assert container.thread_lock("thread-a") is first
    assert first is not second


def test_closed_connection_reports_error(settings):
    instance = ChatbotContainer(settings)
    instance.close()

    with pytest.raises(psycopg.OperationalError):
        instance.connection.execute("SELECT 1")
