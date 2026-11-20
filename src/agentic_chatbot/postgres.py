"""Connection handling and schema setup for PostgreSQL.

This is the Postgres counterpart to :mod:`agentic_chatbot.database`. The two
modules intentionally expose the same three entry points — ``create_connection``,
``connection_lock`` and ``init_schema`` — so the container can pick a backend
without any service knowing which one it got.

Dialect notes:

* psycopg uses ``%s`` placeholders, not ``?``. Because the repository SQL is
  written with ``?`` (so the SQLite path stays untouched), every statement goes
  through :func:`translate` at execution time. That is one regex per statement,
  which is far cheaper than maintaining two copies of every query.
* ``TIMESTAMPTZ`` is rendered back as ``"YYYY-MM-DD HH:MM:SS"`` text, matching
  what SQLite's ``CURRENT_TIMESTAMP`` produced. Models keep ``str | None``, the
  API payloads do not change, and the frontend's timestamp parser keeps working.
"""

from __future__ import annotations

import re
import threading

import psycopg
from psycopg.rows import dict_row

from agentic_chatbot import postgres_schema

# `?` is a literal in Postgres, so only bare placeholders are rewritten. The
# repository SQL never contains a literal `?` inside a string.
_PLACEHOLDER = re.compile(r"\?")


def translate(sql: str) -> str:
    """Convert the repository's ``?`` placeholders to psycopg's ``%s``."""
    return _PLACEHOLDER.sub("%s", sql)


def create_connection(dsn: str) -> psycopg.Connection:
    """Open a connection whose rows behave like ``sqlite3.Row``.

    ``dict_row`` gives mapping access (``row["thread_id"]``), which is how the
    repositories read results, so the conversion helpers need no branching.

    Autocommit stays **off**: the repositories rely on real transactions, and
    ``replace_document`` depends on ``rollback()`` to avoid half-written chunks.
    The one statement that cannot run in a transaction
    (``CREATE INDEX CONCURRENTLY``, issued by LangGraph's ``setup()``) is handled
    by :func:`run_outside_transaction` rather than by weakening every other
    write.
    """
    connection = psycopg.connect(dsn, row_factory=dict_row, autocommit=False)
    return connection


def run_outside_transaction(connection: Any, action: Any) -> Any:
    """Run ``action`` with autocommit temporarily on, then restore it.

    ``PostgresSaver.setup()`` creates an index with ``CREATE INDEX
    CONCURRENTLY``, which Postgres refuses inside a transaction block. Rather
    than make the whole connection autocommit — which would silently disable
    ``rollback()`` for the application's writes — autocommit is enabled only for
    the duration of setup.

    Autocommit is a property of the *connection*, and this connection is shared
    with the repositories, the vector store and the checkpointer. The switch is
    therefore made while holding the connection's lock: otherwise another thread
    could issue a statement between the commit and the restore and have it
    silently auto-committed. The lock is reentrant, so an ``action`` that takes
    it again (``PostgresSaver.setup`` does) still works.
    """
    lock = connection_lock(connection)

    with lock:
        previous = connection.autocommit

        if previous:
            return action()

        connection.commit()  # close anything implicitly open
        connection.autocommit = True

        try:
            return action()
        finally:
            connection.autocommit = previous


_LOCKS: dict[int, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def connection_lock(connection: psycopg.Connection) -> threading.RLock:
    """One lock per connection, for the same reason the SQLite path needs it.

    psycopg connections are not safe to share across threads concurrently, and
    the repositories deliberately share one connection so their statements land
    in one transaction. The lock therefore belongs to the connection.
    """
    key = id(connection)

    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)

        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock

        return lock


def init_schema(
    connection: psycopg.Connection,
    *,
    embedding_dimensions: int = 1536,
) -> None:
    lock = connection_lock(connection)

    with lock:
        with connection.cursor() as cursor:
            for statement in postgres_schema.ALL_STATEMENTS:
                cursor.execute(statement)

            # pgvector is optional: these statements no-op when the extension is
            # absent, so an installation without it still starts.
            cursor.execute(postgres_schema.pgvector_setup(embedding_dimensions))
            cursor.execute(postgres_schema.PGVECTOR_BACKFILL)
            connection.commit()

        _check_embedding_dimensions(connection, embedding_dimensions)
        connection.commit()


def _check_embedding_dimensions(
    connection: psycopg.Connection,
    embedding_dimensions: int,
) -> None:
    """Refuse to mix vector sizes, exactly as the SQLite path does."""
    lock = connection_lock(connection)

    with lock:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT value FROM rag_meta WHERE key = %s",
                ("embedding_dimensions",),
            )
            stored = cursor.fetchone()

            if stored is None:
                cursor.execute(
                    "INSERT INTO rag_meta (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO NOTHING",
                    ("embedding_dimensions", str(embedding_dimensions)),
                )
            elif int(stored["value"]) != embedding_dimensions:
                raise RuntimeError(
                    "Embedding dimension changed from "
                    f"{stored['value']} to {embedding_dimensions}. Delete the "
                    "documents, document_chunks, and rag_meta rows plus "
                    "data/faiss/*.faiss, then re-ingest."
                )

            cursor.execute(
                "INSERT INTO rag_meta (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO NOTHING",
                ("index_format_version", "1"),
            )
