"""SQLite repositories for thread metadata and notes."""

import sqlite3
import uuid
from collections.abc import Sequence

from agentic_chatbot.models import Chunk, Document, Note, Thread

_SELECT_COLUMNS = "thread_id, title, created_at, updated_at"
_NOTE_COLUMNS = "note_id, thread_id, title, content, created_at"
_DOCUMENT_COLUMNS = (
    "doc_id, namespace, source, title, content_hash, size_bytes, "
    "created_at, updated_at"
)


def _to_thread(row: sqlite3.Row) -> Thread:
    return Thread(
        thread_id=row["thread_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ThreadRepository:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._cursor = connection.cursor()

    def create(self, title: str = "New chat") -> Thread:
        thread_id = str(uuid.uuid4())
        self._cursor.execute(
            "INSERT INTO threads (thread_id, title) VALUES (?, ?)",
            (thread_id, title),
        )
        self._connection.commit()
        return self.get(thread_id)

    def get(self, thread_id: str) -> Thread | None:
        row = self._cursor.execute(
            f"SELECT {_SELECT_COLUMNS} FROM threads WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        return _to_thread(row) if row else None

    def list_all(self) -> list[Thread]:
        rows = self._cursor.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM threads
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
        return [_to_thread(row) for row in rows]

    def exists(self, thread_id: str) -> bool:
        row = self._cursor.execute(
            "SELECT 1 FROM threads WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        return row is not None

    def update_title(self, thread_id: str, title: str) -> None:
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
        self._cursor.execute(
            "DELETE FROM threads WHERE thread_id = ?",
            (thread_id,),
        )
        self._connection.commit()


def _to_note(row: sqlite3.Row) -> Note:
    return Note(
        note_id=row["note_id"],
        thread_id=row["thread_id"],
        title=row["title"],
        content=row["content"],
        created_at=row["created_at"],
    )


class NotesRepository:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._cursor = connection.cursor()

    def create(self, thread_id: str, title: str, content: str) -> Note:
        note_id = str(uuid.uuid4())
        self._cursor.execute(
            """
            INSERT INTO notes (note_id, thread_id, title, content)
            VALUES (?, ?, ?, ?)
            """,
            (note_id, thread_id, title, content),
        )
        self._connection.commit()
        return self.get(thread_id, note_id)

    def get(self, thread_id: str, note_id: str) -> Note | None:
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
        pattern = f"%{query}%"
        rows = self._cursor.execute(
            f"""
            SELECT {_NOTE_COLUMNS}
            FROM notes
            WHERE thread_id = ? AND (title LIKE ? OR content LIKE ?)
            ORDER BY created_at ASC, note_id ASC
            """,
            (thread_id, pattern, pattern),
        ).fetchall()
        return [_to_note(row) for row in rows]

    def delete(self, thread_id: str, note_id: str) -> bool:
        self._cursor.execute(
            "DELETE FROM notes WHERE thread_id = ? AND note_id = ?",
            (thread_id, note_id),
        )
        self._connection.commit()
        return self._cursor.rowcount > 0


def _to_document(row: sqlite3.Row) -> Document:
    return Document(
        doc_id=row["doc_id"],
        namespace=row["namespace"],
        source=row["source"],
        title=row["title"],
        content_hash=row["content_hash"],
        size_bytes=row["size_bytes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class DocumentsRepository:
    """Owns every SQL statement for documents and their chunks.

    Vectors are not stored here; ``document_chunks.row_id`` is the id the FAISS
    index refers to.
    """

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._cursor = connection.cursor()

    def get(self, doc_id: str) -> Document | None:
        row = self._cursor.execute(
            f"SELECT {_DOCUMENT_COLUMNS} FROM documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        return _to_document(row) if row else None

    def find_by_source(self, namespace: str, source: str) -> Document | None:
        row = self._cursor.execute(
            f"""
            SELECT {_DOCUMENT_COLUMNS}
            FROM documents
            WHERE namespace = ? AND source = ?
            """,
            (namespace, source),
        ).fetchone()
        return _to_document(row) if row else None

    def list_documents(self, namespace: str | None = None) -> list[Document]:
        if namespace is None:
            rows = self._cursor.execute(
                f"""
                SELECT {_DOCUMENT_COLUMNS}
                FROM documents
                ORDER BY namespace ASC, source ASC
                """
            ).fetchall()
        else:
            rows = self._cursor.execute(
                f"""
                SELECT {_DOCUMENT_COLUMNS}
                FROM documents
                WHERE namespace = ?
                ORDER BY source ASC
                """,
                (namespace,),
            ).fetchall()

        return [_to_document(row) for row in rows]

    def list_namespaces(self) -> list[str]:
        rows = self._cursor.execute(
            "SELECT DISTINCT namespace FROM documents ORDER BY namespace"
        ).fetchall()
        return [row[0] for row in rows]

    def replace_document(
        self,
        namespace: str,
        source: str,
        title: str,
        content_hash: str,
        size_bytes: int,
        chunks: Sequence[Chunk],
    ) -> tuple[Document, list[int]]:
        existing = self.find_by_source(namespace, source)

        try:
            if existing is None:
                doc_id = str(uuid.uuid4())
                self._cursor.execute(
                    """
                    INSERT INTO documents
                        (doc_id, namespace, source, title, content_hash,
                         size_bytes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc_id,
                        namespace,
                        source,
                        title,
                        content_hash,
                        size_bytes,
                    ),
                )
            else:
                doc_id = existing.doc_id
                self._cursor.execute(
                    """
                    UPDATE documents
                    SET title = ?, content_hash = ?, size_bytes = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE doc_id = ?
                    """,
                    (title, content_hash, size_bytes, doc_id),
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
                )
                row_ids.append(int(self._cursor.lastrowid))

            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

        document = self.get(doc_id)

        if document is None:  # pragma: no cover - guarded by the transaction
            raise RuntimeError("document disappeared during replace")

        return document, row_ids

    def chunk_ids(self, doc_id: str) -> list[int]:
        rows = self._cursor.execute(
            """
            SELECT row_id
            FROM document_chunks
            WHERE doc_id = ?
            ORDER BY chunk_index ASC
            """,
            (doc_id,),
        ).fetchall()
        return [int(row[0]) for row in rows]

    def list_chunks(self, namespace: str) -> list[tuple[int, str]]:
        """Return ``(row_id, content)`` for every chunk in one namespace."""
        rows = self._cursor.execute(
            """
            SELECT row_id, content
            FROM document_chunks
            WHERE namespace = ?
            ORDER BY row_id ASC
            """,
            (namespace,),
        ).fetchall()
        return [(int(row[0]), row[1]) for row in rows]

    def chunks_fingerprint(self, namespace: str) -> tuple[int, int, int]:
        """Cheap signature of a namespace's chunks used to detect staleness.

        Any insert, delete, or replacement changes it: chunk ids are
        auto-increment, so a re-ingest always raises the maximum (and usually the
        count or the sum), and a deletion lowers the count.
        """
        row = self._cursor.execute(
            """
            SELECT COUNT(*), COALESCE(MAX(row_id), 0), COALESCE(SUM(row_id), 0)
            FROM document_chunks
            WHERE namespace = ?
            """,
            (namespace,),
        ).fetchone()
        return (int(row[0]), int(row[1]), int(row[2]))

    def chunks_by_ids(
        self, row_ids: Sequence[int]
    ) -> dict[int, sqlite3.Row]:
        if not row_ids:
            return {}

        placeholders = ", ".join("?" for _ in row_ids)
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
        documents = self._cursor.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0]
        chunks = self._cursor.execute(
            "SELECT COUNT(*) FROM document_chunks"
        ).fetchone()[0]
        namespaces = self._cursor.execute(
            "SELECT COUNT(DISTINCT namespace) FROM documents"
        ).fetchone()[0]

        return {
            "documents": int(documents),
            "chunks": int(chunks),
            "namespaces": int(namespaces),
        }
