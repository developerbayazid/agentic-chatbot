"""Embedding storage in PostgreSQL, using pgvector when it is available.

The interface mirrors :class:`agentic_chatbot.vector_store.VectorIndexStore`
exactly — ``add``, ``replace``, ``remove``, ``search``, ``stats`` — so
``DocumentService`` is unchanged and FAISS remains a fallback for the SQLite
backend.

Two storage modes, chosen automatically
---------------------------------------
**pgvector (preferred).** When the ``vector`` extension exists, embeddings live in
``document_chunks.embedding_vec vector(1536)`` with an HNSW index, and search is
``ORDER BY embedding_vec <=> query`` — an indexed approximate nearest-neighbour
scan. This is the intended production path.

**Arrays (fallback).** Without the extension, the older
``document_chunks.embedding DOUBLE PRECISION[]`` column is used and similarity is
computed in SQL. Correct, but a full scan.

Both paths normalise queries identically and return cosine *similarity*
(``1 - distance``), so scores are comparable across modes and with FAISS's
``IndexFlatIP`` — which is what the retrieval thresholds are tuned against.

The mode is detected once at construction and cached; the extension cannot appear
or vanish while the process runs.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from agentic_chatbot.postgres import connection_lock
from agentic_chatbot.sql_backend import wrap


class PgVectorStore:
    """Embedding store backed by ``document_chunks`` in PostgreSQL."""

    def __init__(self, connection: Any, dimensions: int):
        self._connection = wrap(connection)
        self._dimensions = int(dimensions)
        # The repositories, the checkpointer and this store all share ONE
        # psycopg connection, and a connection runs one command at a time.
        # A lock of our own would therefore protect nothing: two threads
        # holding different locks would each believe they had exclusive use
        # and psycopg would fail with "another command is already in
        # progress". The lock belongs to the connection, so every component
        # must take the same one.
        self._lock = connection_lock(connection)
        self._mode: str | None = None

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def mode(self) -> str:
        """``"pgvector"`` or ``"array"`` — which storage this instance uses."""
        if self._mode is None:
            self._mode = self._detect_mode()
        return self._mode

    def add(
        self,
        namespace: str,
        ids: Sequence[int],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        if not ids:
            return

        self._write(ids, vectors)

    def replace(
        self,
        namespace: str,
        remove_ids: Sequence[int],
        add_ids: Sequence[int],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        # The repository already deleted the document's chunks and inserted new
        # ones, so `remove_ids` refers to rows that no longer exist.
        if add_ids:
            self._write(add_ids, vectors)

    def remove(self, namespace: str, ids: Sequence[int]) -> None:
        if not ids:
            return

        placeholders = ", ".join("?" for _ in ids)
        column = self._column

        with self._lock:
            self._connection.cursor().execute(
                f"UPDATE document_chunks SET {column} = NULL "
                f"WHERE row_id IN ({placeholders})",
                tuple(ids),
            )
            self._connection.commit()

    def search(
        self,
        namespaces: Sequence[str],
        vector: Sequence[float],
        k: int,
    ) -> list[tuple[int, float]]:
        """Return ``(chunk_row_id, cosine_similarity)`` ordered best first."""
        if k <= 0 or not namespaces:
            return []

        normalised = _normalise(vector, self._dimensions)

        if self.mode == "pgvector":
            return self._search_pgvector(namespaces, normalised, k)

        return self._search_array(namespaces, normalised, k)

    def stats(self) -> dict[str, int]:
        """Chunk counts per namespace that actually carry a vector."""
        column = self._column

        with self._lock:
            rows = self._connection.cursor().execute(
                f"""
                SELECT namespace, COUNT(*) AS n
                FROM document_chunks
                WHERE {column} IS NOT NULL
                GROUP BY namespace
                """
            ).fetchall()

        return {row["namespace"]: int(row["n"]) for row in rows}

    def probe(self) -> bool:
        """Cheap readiness check: is the embedding column reachable?

        Deliberately narrower than ``stats()`` — readiness runs on every probe and
        must not aggregate the whole corpus. ``LIMIT 0`` still validates that the
        connection is live and the column exists.
        """
        try:
            column = self._column

            with self._lock:
                self._connection.cursor().execute(
                    f"SELECT {column} FROM document_chunks LIMIT 0"
                )

            return True
        except Exception:  # noqa: BLE001 - an unreachable store is not ready
            return False

    # ------------------------------------------------------------------ internals

    @property
    def _column(self) -> str:
        return "embedding_vec" if self.mode == "pgvector" else "embedding"

    def _detect_mode(self) -> str:
        """Use pgvector when the extension is installed, otherwise fall back."""
        try:
            with self._lock:
                row = self._connection.cursor().execute(
                    "SELECT 1 AS present FROM pg_extension WHERE extname = 'vector'"
                ).fetchone()

            if row is not None:
                return "pgvector"
        except Exception:  # noqa: BLE001 - treat any failure as "not available"
            pass

        return "array"

    def _search_pgvector(
        self,
        namespaces: Sequence[str],
        normalised: list[float],
        k: int,
    ) -> list[tuple[int, float]]:
        """Indexed ANN search. ``<=>`` is cosine distance, so similarity is 1-d."""
        placeholders = ", ".join("?" for _ in namespaces)
        literal = _pg_vector(normalised)

        sql = f"""
            SELECT row_id, 1 - (embedding_vec <=> ?::vector) AS score
            FROM document_chunks
            WHERE namespace IN ({placeholders})
              AND embedding_vec IS NOT NULL
            ORDER BY embedding_vec <=> ?::vector
            LIMIT ?
        """

        with self._lock:
            rows = self._connection.cursor().execute(
                sql, (literal, *namespaces, literal, k)
            ).fetchall()

        return [(int(row["row_id"]), float(row["score"])) for row in rows]

    def _search_array(
        self,
        namespaces: Sequence[str],
        normalised: list[float],
        k: int,
    ) -> list[tuple[int, float]]:
        """Fallback: cosine similarity computed over the namespace's rows."""
        placeholders = ", ".join("?" for _ in namespaces)

        sql = f"""
            SELECT row_id,
                   COALESCE((
                       SELECT SUM(a * b)
                       FROM unnest(embedding, ?::double precision[]) AS t(a, b)
                   ), 0) AS score
            FROM document_chunks
            WHERE namespace IN ({placeholders})
              AND embedding IS NOT NULL
              AND array_length(embedding, 1) = ?
            ORDER BY score DESC
            LIMIT ?
        """

        with self._lock:
            rows = self._connection.cursor().execute(
                sql, (list(normalised), *namespaces, self._dimensions, k)
            ).fetchall()

        return [(int(row["row_id"]), float(row["score"])) for row in rows]

    def _write(self, ids: Sequence[int], vectors: Sequence[Sequence[float]]) -> None:
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors must be the same length")

        normalised = [_normalise(vector, self._dimensions) for vector in vectors]
        column = self._column
        pgvector = self.mode == "pgvector"
        cast = "vector" if pgvector else "double precision[]"

        with self._lock:
            cursor = self._connection.cursor()

            for row_id, vector in zip(ids, normalised):
                value: Any = _pg_vector(vector) if pgvector else vector
                cursor.execute(
                    f"UPDATE document_chunks SET {column} = ?::{cast} "
                    f"WHERE row_id = ?",
                    (value, row_id),
                )

            self._connection.commit()


def _normalise(vector: Sequence[float], dimensions: int) -> list[float]:
    """L2-normalise, matching FAISS's ``normalize_L2``."""
    values = [float(value) for value in vector]

    if len(values) != dimensions:
        raise ValueError(
            f"vector has {len(values)} dimensions; expected {dimensions}"
        )

    norm = math.sqrt(sum(value * value for value in values))

    if norm == 0:
        return values

    return [value / norm for value in values]


def _pg_vector(values: Sequence[float]) -> str:
    """Render a Python list as a pgvector literal: ``[1,2,3]``."""
    return "[" + ",".join(repr(float(value)) for value in values) + "]"
