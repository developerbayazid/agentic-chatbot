"""Embedding storage in PostgreSQL, replacing the on-disk FAISS indexes.

The interface mirrors :class:`agentic_chatbot.vector_store.VectorIndexStore`
exactly — ``add``, ``replace``, ``remove``, ``search``, ``stats`` — so
``DocumentService`` is unchanged and FAISS remains a fallback flag.

Storage format
--------------
Embeddings are stored as ``double precision[]`` in ``document_chunks.embedding``
rather than a ``vector`` column. That is a deliberate, documented trade-off:

* **pgvector is not installed.** ``CREATE EXTENSION vector`` fails on this
  server ("extension is not available"), and it cannot be built here because
  there is no C toolchain. A ``vector`` column would simply not work.
* An array column needs no extension, so vectors travel with the rows they
  belong to, in the same transaction and the same backup.
* Cosine similarity is computed in SQL over the candidate set, after the owner
  filter, so the security-relevant property (another user's chunk can neither be
  returned nor influence ordering) is unchanged.

Cost: search is a full scan of the namespace's chunks rather than an indexed
approximate search. That is fine at this corpus size (hundreds of chunks) and is
the honest limitation to fix when pgvector becomes available. ``SEARCH_INDEX`` in
the docs records this. The conversion is mechanical: the same normalised vectors
go into a ``vector(1536)`` column and the ORDER BY becomes ``<=>``.

Vectors are L2-normalised before storage, matching what FAISS received
(``IndexFlatIP`` on normalised vectors == cosine similarity), so scores from the
two backends are directly comparable.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from typing import Any

from agentic_chatbot.sql_backend import wrap


class PgVectorStore:
    """Embedding store backed by ``document_chunks`` in PostgreSQL."""

    def __init__(self, connection: Any, dimensions: int):
        self._connection = wrap(connection)
        self._dimensions = int(dimensions)
        self._lock = threading.Lock()

    @property
    def dimensions(self) -> int:
        return self._dimensions

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
        # The repository already deletes the document's chunks and inserts the new
        # ones, so `remove_ids` refers to rows that no longer exist. Nothing to do
        # for them; writing the new vectors is the whole operation.
        if add_ids:
            self._write(add_ids, vectors)

    def remove(self, namespace: str, ids: Sequence[int]) -> None:
        if not ids:
            return

        placeholders = ", ".join("?" for _ in ids)

        with self._lock:
            self._connection.cursor().execute(
                f"UPDATE document_chunks SET embedding = NULL "
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
        """Return ``(chunk_row_id, cosine_similarity)`` ordered best first.

        The query is normalised exactly as stored vectors were, so a dot product
        is the cosine similarity. Rows without an embedding are skipped.
        """
        if k <= 0 or not namespaces:
            return []

        normalised = _normalise(vector, self._dimensions)
        placeholders = ", ".join("?" for _ in namespaces)

        # Cosine similarity over the candidate set. `array_length` guards against
        # a row written by an older configuration with a different size.
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
                sql,
                (list(normalised), *namespaces, self._dimensions, k),
            ).fetchall()

        return [(int(row["row_id"]), float(row["score"])) for row in rows]

    def stats(self) -> dict[str, int]:
        """Chunk counts per namespace that actually carry a vector."""
        with self._lock:
            rows = self._connection.cursor().execute(
                """
                SELECT namespace, COUNT(*) AS n
                FROM document_chunks
                WHERE embedding IS NOT NULL
                GROUP BY namespace
                """
            ).fetchall()

        return {row["namespace"]: int(row["n"]) for row in rows}

    def probe(self) -> bool:
        """Cheap readiness check: is the embedding column reachable?

        Deliberately narrower than ``stats()`` — readiness runs on every probe and
        must not aggregate the whole corpus. ``LIMIT 0`` still validates that the
        connection is live and the column exists, which is what "ready" means here.
        """
        try:
            self._connection.cursor().execute(
                "SELECT embedding FROM document_chunks LIMIT 0"
            )
            return True
        except Exception:  # noqa: BLE001 - an unreachable store is not ready
            return False

    def _write(self, ids: Sequence[int], vectors: Sequence[Sequence[float]]) -> None:
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors must be the same length")

        normalised = [_normalise(vector, self._dimensions) for vector in vectors]

        with self._lock:
            cursor = self._connection.cursor()

            for row_id, vector in zip(ids, normalised):
                cursor.execute(
                    "UPDATE document_chunks SET embedding = ?::double precision[] "
                    "WHERE row_id = ?",
                    (_pg_array(vector), row_id),
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


def _pg_array(values: Sequence[float]) -> str:
    """Render a Python list as a Postgres array literal."""
    return "{" + ",".join(repr(float(value)) for value in values) + "}"
