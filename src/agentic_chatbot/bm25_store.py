"""In-memory BM25 keyword indexes rebuilt from the SQLite chunk table.

SQLite stays authoritative for document text. This store only caches a BM25
index per namespace and rebuilds it when the namespace's chunk set changes, so
there is no second copy of the data to persist, migrate, or corrupt.

The cache is process-local: after a restart the first search for a namespace
rebuilds its index from ``document_chunks``.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from agentic_chatbot.repository import DocumentsRepository

_LOGGER = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# rank_bm25 uses the idf variant without the "+1" smoothing, so on tiny
# corpora a term that appears in most documents gets an idf of zero or, after
# rank_bm25's epsilon correction, a negative value. Either would make a real
# keyword match score <= 0 and be dropped. Clamping to a small positive value
# keeps "contains the term" ranked above "does not".
_IDF_FLOOR = 1e-6


def tokenize(text: str) -> list[str]:
    """Split text into lowercase alphanumeric terms.

    Employee IDs, product codes, and technical names survive tokenization as
    their component parts (``EMP-1042`` -> ``["emp", "1042"]``), so exact
    identifiers remain searchable.
    """
    return _TOKEN_RE.findall(text.lower())


@dataclass
class _NamespaceIndex:
    fingerprint: tuple[int, int, int]
    row_ids: list[int]
    index: BM25Okapi


class BM25IndexStore:
    """One lazily built BM25 index per namespace, sourced from SQLite."""

    def __init__(
        self,
        repository: DocumentsRepository,
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        self._repository = repository
        self._k1 = k1
        self._b = b
        self._indexes: dict[str, _NamespaceIndex] = {}
        self._lock = threading.Lock()

    def search(
        self,
        namespaces: Sequence[str],
        query: str,
        k: int,
    ) -> list[tuple[int, float]]:
        """Return ``(chunk_row_id, bm25_score)`` ordered best first."""
        if k <= 0 or not namespaces:
            return []

        tokens = tokenize(query)

        if not tokens:
            return []

        results: list[tuple[int, float]] = []

        with self._lock:
            for namespace in dict.fromkeys(namespaces):
                cached = self._get(namespace)

                if cached is None:
                    continue

                scores = cached.index.get_scores(tokens)

                for row_id, score in zip(cached.row_ids, scores):
                    value = float(score)

                    if value > 0:
                        results.append((row_id, value))

        results.sort(key=lambda item: (-item[1], item[0]))
        return results[:k]

    def invalidate(self, namespace: str | None = None) -> None:
        """Drop cached indexes so the next search rebuilds them from SQLite."""
        with self._lock:
            if namespace is None:
                self._indexes.clear()
            else:
                self._indexes.pop(namespace, None)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                namespace: len(cached.row_ids)
                for namespace, cached in self._indexes.items()
            }

    def _get(self, namespace: str) -> _NamespaceIndex | None:
        fingerprint = self._repository.chunks_fingerprint(namespace)
        cached = self._indexes.get(namespace)

        if cached is not None and cached.fingerprint == fingerprint:
            return cached

        if fingerprint[0] == 0:
            self._indexes.pop(namespace, None)
            return None

        chunks = self._repository.list_chunks(namespace)

        if not chunks:
            self._indexes.pop(namespace, None)
            return None

        corpus = [tokenize(content) for _, content in chunks]

        if not any(corpus):
            self._indexes.pop(namespace, None)
            return None

        row_ids = [row_id for row_id, _ in chunks]
        index = BM25Okapi(corpus, k1=self._k1, b=self._b)

        for term, value in list(index.idf.items()):
            if value <= 0:
                index.idf[term] = _IDF_FLOOR

        _LOGGER.debug(
            "built BM25 index for namespace %r (%d chunks)",
            namespace,
            len(row_ids),
        )
        self._indexes[namespace] = _NamespaceIndex(fingerprint, row_ids, index)
        return self._indexes[namespace]
