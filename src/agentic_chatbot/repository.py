"""Repositories for thread metadata, notes, documents, and their chunks.

All repositories share one connection (and therefore one transaction), so they
also share one lock. Holding a lock per repository would not protect anything: a
commit in one thread would still commit another thread's open transaction.

The SQL below is written once against :mod:`agentic_chatbot.sql_backend`, which
adapts it to either SQLite or PostgreSQL. Only three constructs differ between
the engines, and each is handled explicitly rather than abstracted away:

* generated ids — ``execute(..., returning="row_id")``
* timestamps — normalised back to ``"YYYY-MM-DD HH:MM:SS"``
* placeholders — translated by the adapter
"""

import uuid
from collections.abc import Sequence
from typing import Any

from agentic_chatbot.database import connection_lock
from agentic_chatbot.models import Chunk, Document, Note, Thread
from agentic_chatbot.postgres import connection_lock as postgres_connection_lock
from agentic_chatbot.sql_backend import sqlite_backend, wrap

_SELECT_COLUMNS = "thread_id, title, owner_id, created_at, updated_at"
_NOTE_COLUMNS = "note_id, thread_id, title, content, created_at"
_DOCUMENT_COLUMNS = (
    "doc_id, namespace, source, title, content_hash, size_bytes, owner_id, "
    "created_at, updated_at"
)


def _to_thread(row: Any) -> Thread:
    return Thread(
        thread_id=row["thread_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        owner_id=row["owner_id"],
    )


def _to_note(row: Any) -> Note:
    return Note(
        note_id=row["note_id"],
        thread_id=row["thread_id"],
        title=row["title"],
        content=row["content"],
        created_at=row["created_at"],
    )


def _to_document(row: Any) -> Document:
    return Document(
        doc_id=row["doc_id"],
        namespace=row["namespace"],
        source=row["source"],
        title=row["title"],
        content_hash=row["content_hash"],
        size_bytes=row["size_bytes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        owner_id=row["owner_id"],
    )


class _Repository:
    """Shared plumbing: one connection, one cursor, one lock."""

    def __init__(self, connection: Any):
        self._connection = wrap(connection)
        self._cursor = self._connection.cursor()
        self._lock = (
            connection_lock(connection)
            if sqlite_backend(connection)
            else postgres_connection_lock(connection)
        )


class ThreadRepository(_Repository):
    def create(self, title: str = "New chat", owner_id: str | None = None) -> Thread:
        with self._lock:
            thread_id = str(uuid.uuid4())
            self._cursor.execute(
                "INSERT INTO threads (thread_id, title, owner_id) "
                "VALUES (?, ?, ?)",
                (thread_id, title, owner_id),
            )
            self._connection.commit()
            return self.get(thread_id)  # type: ignore[return-value]

    def get(self, thread_id: str) -> Thread | None:
        with self._lock:
            row = self._cursor.execute(
                f"SELECT {_SELECT_COLUMNS} FROM threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            return _to_thread(row) if row else None

    def list_all(self, owner_id: str | None = None) -> list[Thread]:
        with self._lock:
            if owner_id is None:
                rows = self._cursor.execute(
                    f"""
                    SELECT {_SELECT_COLUMNS}
                    FROM threads
                    ORDER BY updated_at DESC, created_at DESC
                    """
                ).fetchall()
            else:
                rows = self._cursor.execute(
                    f"""
                    SELECT {_SELECT_COLUMNS}
                    FROM threads
                    WHERE owner_id = ?
                    ORDER BY updated_at DESC, created_at DESC
                    """,
                    (owner_id,),
                ).fetchall()

            return [_to_thread(row) for row in rows]

    def exists(self, thread_id: str) -> bool:
        with self._lock:
            row = self._cursor.execute(
                "SELECT 1 AS present FROM threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            return row is not None

    def update_title(self, thread_id: str, title: str) -> None:
        with self._lock:
            self._cursor.execute(
                """
                UPDATE threads
                SET title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE thread_id = ?
                """,
                (title, thread_id),
            )
            self._connection.commit()

    def touch(self, thread_id: str) -> None:
        with self._lock:
            self._cursor.execute(
                """
                UPDATE threads
                SET updated_at = CURRENT_TIMESTAMP
                WHERE thread_id = ?
                """,
                (thread_id,),
            )
            self._connection.commit()

    def delete(self, thread_id: str) -> None:
        with self._lock:
            self._cursor.execute(
                "DELETE FROM threads WHERE thread_id = ?",
                (thread_id,),
            )
            self._connection.commit()


class NotesRepository(_Repository):
    def create(self, thread_id: str, title: str, content: str) -> Note:
        with self._lock:
            note_id = str(uuid.uuid4())
            self._cursor.execute(
                """
                INSERT INTO notes (note_id, thread_id, title, content)
                VALUES (?, ?, ?, ?)
                """,
                (note_id, thread_id, title, content),
            )
            self._connection.commit()
            return self.get(thread_id, note_id)  # type: ignore[return-value]

    def get(self, thread_id: str, note_id: str) -> Note | None:
        with self._lock:
            row = self._cursor.execute(
                f"""
                SELECT {_NOTE_COLUMNS}
                FROM notes
                WHERE thread_id = ? AND note_id = ?
                """,
                (thread_id, note_id),
            ).fetchone()
            return _to_note(row) if row else None

    def list_all(self, thread_id: str) -> list[Note]:
        with self._lock:
            rows = self._cursor.execute(
                f"""
                SELECT {_NOTE_COLUMNS}
                FROM notes
                WHERE thread_id = ?
                ORDER BY created_at ASC, note_id ASC
                """,
                (thread_id,),
            ).fetchall()
            return [_to_note(row) for row in rows]

    def search(self, thread_id: str, query: str) -> list[Note]:
        with self._lock:
            # `ILIKE` is Postgres-only and `LIKE` is case-insensitive in SQLite by
            # default, so LOWER() on both sides is the one portable formulation.
            pattern = f"%{query.lower()}%"
            rows = self._cursor.execute(
                f"""
                SELECT {_NOTE_COLUMNS}
                FROM notes
                WHERE thread_id = ?
                  AND (LOWER(title) LIKE ? OR LOWER(content) LIKE ?)
                ORDER BY created_at ASC, note_id ASC
                """,
                (thread_id, pattern, pattern),
            ).fetchall()
            return [_to_note(row) for row in rows]

    def delete(self, thread_id: str, note_id: str) -> bool:
        with self._lock:
            self._cursor.execute(
                "DELETE FROM notes WHERE thread_id = ? AND note_id = ?",
                (thread_id, note_id),
            )
            self._connection.commit()
            return self._cursor.rowcount > 0


class DocumentsRepository(_Repository):
    """Owns every SQL statement for documents and their chunks.

    Vectors are not stored here; ``document_chunks.row_id`` is the id the FAISS
    index refers to.
    """

    def get(self, doc_id: str) -> Document | None:
        with self._lock:
            row = self._cursor.execute(
                f"SELECT {_DOCUMENT_COLUMNS} FROM documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            return _to_document(row) if row else None

    def find_by_source(self, namespace: str, source: str) -> Document | None:
        with self._lock:
            row = self._cursor.execute(
                f"""
                SELECT {_DOCUMENT_COLUMNS}
                FROM documents
                WHERE namespace = ? AND source = ?
                """,
                (namespace, source),
            ).fetchone()
            return _to_document(row) if row else None

    def list_documents(
        self, namespace: str | None = None, owner_id: str | None = None
    ) -> list[Document]:
        clauses: list[str] = []
        parameters: list[str] = []

        if namespace is not None:
            clauses.append("namespace = ?")
            parameters.append(namespace)

        if owner_id is not None:
            clauses.append("owner_id = ?")
            parameters.append(owner_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._lock:
            rows = self._cursor.execute(
                f"""
                SELECT {_DOCUMENT_COLUMNS}
                FROM documents
                {where}
                ORDER BY namespace ASC, source ASC
                """,
                tuple(parameters),
            ).fetchall()

            return [_to_document(row) for row in rows]

    def list_namespaces(self, owner_id: str | None = None) -> list[str]:
        with self._lock:
            if owner_id is None:
                rows = self._cursor.execute(
                    "SELECT DISTINCT namespace FROM documents ORDER BY namespace"
                ).fetchall()
            else:
                rows = self._cursor.execute(
                    """
                    SELECT DISTINCT namespace
                    FROM documents
                    WHERE owner_id = ?
                    ORDER BY namespace
                    """,
                    (owner_id,),
                ).fetchall()

            return [row["namespace"] for row in rows]

    def authorized_chunk_ids(
        self, owner_id: str, namespaces: Sequence[str]
    ) -> set[int]:
        """Row ids in ``namespaces`` that belong to ``owner_id``.

        Retrieval filters its candidate rankings with this set *before* fusing
        them, so another user's chunk can neither be returned nor influence the
        order of an authorized one.
        """
        if not namespaces:
            return set()

        placeholders = ", ".join("?" for _ in namespaces)

        with self._lock:
            rows = self._cursor.execute(
                f"""
                SELECT c.row_id
                FROM document_chunks c
                JOIN documents d ON d.doc_id = c.doc_id
                WHERE d.owner_id = ? AND c.namespace IN ({placeholders})
                """,
                (owner_id, *namespaces),
            ).fetchall()

            return {int(row["row_id"]) for row in rows}

    def replace_document(
        self,
        namespace: str,
        source: str,
        title: str,
        content_hash: str,
        size_bytes: int,
        chunks: Sequence[Chunk],
        owner_id: str | None = None,
    ) -> tuple[Document, list[int]]:
        with self._lock:
            existing = self.find_by_source(namespace, source)

            try:
                if existing is None:
                    doc_id = str(uuid.uuid4())
                    self._cursor.execute(
                        """
                        INSERT INTO documents
                            (doc_id, namespace, source, title, content_hash,
                             size_bytes, owner_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            doc_id,
                            namespace,
                            source,
                            title,
                            content_hash,
                            size_bytes,
                            owner_id,
                        ),
                    )
                else:
                    doc_id = existing.doc_id
                    self._cursor.execute(
                        """
                        UPDATE documents
                        SET title = ?, content_hash = ?, size_bytes = ?,
                            owner_id = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE doc_id = ?
                        """,
                        (title, content_hash, size_bytes, owner_id, doc_id),
                    )
                    self._cursor.execute(
                        "DELETE FROM document_chunks WHERE doc_id = ?",
                        (doc_id,),
                    )

                row_ids: list[int] = []

                for index, chunk in enumerate(chunks):
                    self._cursor.execute(
                        """
                        INSERT INTO document_chunks
                            (chunk_id, doc_id, namespace, chunk_index, page,
                             content)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            doc_id,
                            namespace,
                            index,
                            chunk.page,
                            chunk.content,
                        ),
                        returning="row_id",
                    )
                    row_ids.append(int(self._cursor.lastrowid or 0))

                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

            document = self.get(doc_id)

            if document is None:  # pragma: no cover - guarded by the transaction
                raise RuntimeError("document disappeared during replace")

            return document, row_ids

    def chunk_ids(self, doc_id: str) -> list[int]:
        with self._lock:
            rows = self._cursor.execute(
                """
                SELECT row_id
                FROM document_chunks
                WHERE doc_id = ?
                ORDER BY chunk_index ASC
                """,
                (doc_id,),
            ).fetchall()
            return [int(row["row_id"]) for row in rows]

    def list_chunks(self, namespace: str) -> list[tuple[int, str]]:
        """Return ``(row_id, content)`` for every chunk in one namespace."""
        with self._lock:
            rows = self._cursor.execute(
                """
                SELECT row_id, content
                FROM document_chunks
                WHERE namespace = ?
                ORDER BY row_id ASC
                """,
                (namespace,),
            ).fetchall()
            return [(int(row["row_id"]), row["content"]) for row in rows]

    def chunks_fingerprint(self, namespace: str) -> tuple[int, int, int]:
        """Cheap signature of a namespace's chunks used to detect staleness.

        Any insert, delete, or replacement changes it: chunk ids are
        auto-increment, so a re-ingest always raises the maximum (and usually the
        count or the sum), and a deletion lowers the count.
        """
        with self._lock:
            row = self._cursor.execute(
                """
                SELECT COUNT(*) AS n, COALESCE(MAX(row_id), 0) AS hi,
                       COALESCE(SUM(row_id), 0) AS total
                FROM document_chunks
                WHERE namespace = ?
                """,
                (namespace,),
            ).fetchone()
            return (int(row["n"]), int(row["hi"]), int(row["total"]))

    def chunks_by_ids(self, row_ids: Sequence[int]) -> dict[int, Any]:
        if not row_ids:
            return {}

        placeholders = ", ".join("?" for _ in row_ids)

        with self._lock:
            rows = self._cursor.execute(
                f"""
                SELECT c.row_id AS row_id, c.chunk_id AS chunk_id,
                       c.doc_id AS doc_id, c.namespace AS namespace,
                       c.chunk_index AS chunk_index, c.page AS page,
                       c.content AS content, d.title AS title, d.source AS source
                FROM document_chunks c
                JOIN documents d ON d.doc_id = c.doc_id
                WHERE c.row_id IN ({placeholders})
                """,
                tuple(row_ids),
            ).fetchall()
            return {int(row["row_id"]): row for row in rows}

    def delete_document(self, doc_id: str) -> bool:
        with self._lock:
            self._cursor.execute(
                "DELETE FROM document_chunks WHERE doc_id = ?",
                (doc_id,),
            )
            self._cursor.execute(
                "DELETE FROM documents WHERE doc_id = ?",
                (doc_id,),
            )
            self._connection.commit()
            return self._cursor.rowcount > 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            documents = self._cursor.execute(
                "SELECT COUNT(*) AS n FROM documents"
            ).fetchone()["n"]
            chunks = self._cursor.execute(
                "SELECT COUNT(*) AS n FROM document_chunks"
            ).fetchone()["n"]
            namespaces = self._cursor.execute(
                "SELECT COUNT(DISTINCT namespace) AS n FROM documents"
            ).fetchone()["n"]

            return {
                "documents": int(documents),
                "chunks": int(chunks),
                "namespaces": int(namespaces),
            }
