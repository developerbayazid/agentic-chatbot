"""SQLite connection and schema setup."""

import sqlite3
import threading

THREADS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    thread_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New chat',
    owner_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

NOTES_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    note_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

NOTES_THREAD_INDEX = """
CREATE INDEX IF NOT EXISTS idx_notes_thread_id ON notes (thread_id)
"""

THREADS_OWNER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_threads_owner ON threads (owner_id)
"""

DOCUMENTS_OWNER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents (owner_id)
"""

DOCUMENTS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    owner_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (namespace, source)
)
"""

DOCUMENT_CHUNKS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS document_chunks (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT NOT NULL UNIQUE,
    doc_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page INTEGER,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

DOCUMENT_CHUNKS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks (doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_namespace ON document_chunks (namespace);
"""

RAG_META_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS rag_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


def create_connection(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(
        database_path,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    return connection


_CONNECTION_LOCKS: dict[int, threading.RLock] = {}
_CONNECTION_LOCKS_GUARD = threading.Lock()


def connection_lock(connection: sqlite3.Connection) -> threading.RLock:
    """Return the lock that serializes access to one connection.

    Every repository on a connection shares one cursor *and* one transaction, so
    the lock has to be keyed to the connection rather than to each repository.
    Two repositories holding separate locks would let one thread commit another
    thread's half-built transaction.
    """
    key = id(connection)

    with _CONNECTION_LOCKS_GUARD:
        lock = _CONNECTION_LOCKS.get(key)

        if lock is None:
            lock = threading.RLock()
            _CONNECTION_LOCKS[key] = lock

        return lock


def init_schema(
    connection: sqlite3.Connection,
    *,
    embedding_dimensions: int = 1536,
) -> None:
    connection.execute(THREADS_TABLE_SCHEMA)
    _migrate_threads_owner_id(connection)
    connection.execute(THREADS_OWNER_INDEX)
    connection.execute(NOTES_TABLE_SCHEMA)
    _migrate_notes_thread_id(connection)
    connection.execute(NOTES_THREAD_INDEX)
    connection.execute(DOCUMENTS_TABLE_SCHEMA)
    _migrate_documents_owner_id(connection)
    connection.execute(DOCUMENTS_OWNER_INDEX)
    connection.execute(DOCUMENT_CHUNKS_TABLE_SCHEMA)
    connection.executescript(DOCUMENT_CHUNKS_INDEXES)
    connection.execute(RAG_META_TABLE_SCHEMA)
    _check_embedding_dimensions(connection, embedding_dimensions)
    connection.commit()


def _check_embedding_dimensions(
    connection: sqlite3.Connection,
    embedding_dimensions: int,
) -> None:
    """Keep stored vectors and the configured embedding size in agreement.

    Changing ``EMBEDDINGS_MODEL`` or ``EMBEDDING_DIMENSIONS`` after documents
    have been indexed would silently mix vector sizes, so it is rejected with
    remediation instead.
    """
    stored = connection.execute(
        "SELECT value FROM rag_meta WHERE key = 'embedding_dimensions'"
    ).fetchone()

    if stored is None:
        connection.execute(
            "INSERT INTO rag_meta (key, value) VALUES (?, ?)",
            ("embedding_dimensions", str(embedding_dimensions)),
        )
    elif int(stored[0]) != embedding_dimensions:
        raise RuntimeError(
            "Embedding dimension changed from "
            f"{stored[0]} to {embedding_dimensions}. Delete the documents, "
            "document_chunks, and rag_meta rows plus data/faiss/*.faiss, "
            "then re-ingest."
        )

    connection.execute(
        "INSERT OR IGNORE INTO rag_meta (key, value) VALUES (?, ?)",
        ("index_format_version", "1"),
    )


def _migrate_notes_thread_id(connection: sqlite3.Connection) -> None:
    """Add thread_id to notes created before notes were thread-scoped.

    Older rows are kept with an empty thread_id, which means they are not
    visible from any conversation.
    """
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(notes)")
    }

    if "thread_id" not in columns:
        connection.execute(
            "ALTER TABLE notes ADD COLUMN thread_id TEXT NOT NULL DEFAULT ''"
        )


def _add_owner_column(connection: sqlite3.Connection, table: str) -> None:
    """Add a nullable owner_id to a table created before owners existed.

    NULL means "no owner": CLI-created threads and pre-API documents stay
    visible to the local operator and to nobody through the REST API.
    """
    columns = {
        row[1] for row in connection.execute(f"PRAGMA table_info({table})")
    }

    if "owner_id" not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN owner_id TEXT")


def _migrate_threads_owner_id(connection: sqlite3.Connection) -> None:
    _add_owner_column(connection, "threads")


def _migrate_documents_owner_id(connection: sqlite3.Connection) -> None:
    _add_owner_column(connection, "documents")
