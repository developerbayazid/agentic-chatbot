"""PostgreSQL schema for the application's relational storage.

Mirrors the SQLite schema table for table, with three deliberate differences:

1. ``document_chunks.row_id`` is ``BIGSERIAL``. SQLite's ``AUTOINCREMENT`` ids are
   never reused; Postgres sequences also do not reuse, so the ids keep the same
   role as FAISS keys and the staleness fingerprint still works.
2. Timestamps are ``TIMESTAMP`` **without** time zone, deliberately. SQLite's
   ``CURRENT_TIMESTAMP`` stores naive UTC text, and a plain ``TIMESTAMP`` column
   preserves exactly that: values round-trip unchanged, so migration is a faithful
   copy and no server timezone can shift them. ``TIMESTAMPTZ`` would reinterpret
   the naive text in the session's zone and silently move every timestamp by the
   server's UTC offset — which the parity tests caught.
3. ``namespace``/``source`` comparisons are case-sensitive in both engines; the
   ``UNIQUE (namespace, source)`` constraint is preserved verbatim.

Everything is ``IF NOT EXISTS`` so applying it twice is a no-op.
"""

from __future__ import annotations

THREADS = """
CREATE TABLE IF NOT EXISTS threads (
    thread_id   TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'New chat',
    owner_id    TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    updated_at  TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')
)
"""

NOTES = """
CREATE TABLE IF NOT EXISTS notes (
    note_id     TEXT PRIMARY KEY,
    thread_id   TEXT NOT NULL DEFAULT '',
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')
)
"""

DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT PRIMARY KEY,
    namespace    TEXT NOT NULL,
    source       TEXT NOT NULL,
    title        TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    owner_id     TEXT,
    created_at   TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    updated_at   TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    CONSTRAINT documents_namespace_source_key UNIQUE (namespace, source)
)
"""

DOCUMENT_CHUNKS = """
CREATE TABLE IF NOT EXISTS document_chunks (
    row_id      BIGSERIAL PRIMARY KEY,
    chunk_id    TEXT NOT NULL UNIQUE,
    doc_id      TEXT NOT NULL,
    namespace   TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page        INTEGER,
    content     TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')
)
"""

RAG_META = """
CREATE TABLE IF NOT EXISTS rag_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_threads_owner ON threads (owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_notes_thread_id ON notes (thread_id)",
    "CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents (owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks (doc_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_namespace ON document_chunks (namespace)",
    # Retrieval joins chunks to documents and filters on the document's owner;
    # without this the owner filter becomes a sequential scan as the corpus grows.
    "CREATE INDEX IF NOT EXISTS idx_documents_owner_namespace "
    "ON documents (owner_id, namespace)",
)

ALL_STATEMENTS = (THREADS, NOTES, DOCUMENTS, DOCUMENT_CHUNKS, RAG_META, *INDEXES)
