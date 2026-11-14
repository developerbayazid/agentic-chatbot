"""Per-namespace FAISS indexes persisted beside the application data."""

from __future__ import annotations

import hashlib
import os
import re
import threading
from collections.abc import Sequence
from pathlib import Path

import faiss
import numpy as np


class VectorIndexStore:
    """One FAISS index file per namespace.

    Vector ids are ``document_chunks.row_id`` values, so a search result joins
    straight back to the SQLite row that produced it.
    """

    def __init__(self, directory: Path, dimensions: int):
        self._directory = Path(directory)
        self._dimensions = int(dimensions)
        self._indexes: dict[str, faiss.IndexIDMap2] = {}
        self._lock = threading.Lock()
        self._directory.mkdir(parents=True, exist_ok=True)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def path_for(self, namespace: str) -> Path:
        return self._directory / _filename(namespace)

    def add(
        self,
        namespace: str,
        ids: Sequence[int],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        if not ids:
            return

        with self._lock:
            index = self._get(namespace)
            self._add(index, ids, vectors)
            self._save(namespace)

    def replace(
        self,
        namespace: str,
        remove_ids: Sequence[int],
        add_ids: Sequence[int],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        with self._lock:
            index = self._get(namespace)

            if remove_ids:
                index.remove_ids(_as_ids(remove_ids))

            if add_ids:
                self._add(index, add_ids, vectors)

            if index.ntotal:
                self._save(namespace)
            else:
                self._drop(namespace)

    def remove(self, namespace: str, ids: Sequence[int]) -> None:
        if not ids:
            return

        with self._lock:
            if namespace not in self._indexes and not self.path_for(namespace).exists():
                return

            index = self._get(namespace)
            index.remove_ids(_as_ids(ids))

            if index.ntotal:
                self._save(namespace)
            else:
                self._drop(namespace)

    def search(
        self,
        namespaces: Sequence[str],
        vector: Sequence[float],
        k: int,
    ) -> list[tuple[int, float]]:
        """Return ``(chunk_row_id, cosine_similarity)`` ordered best first."""
        if k <= 0 or not namespaces:
            return []

        query = np.asarray([vector], dtype="float32")
        faiss.normalize_L2(query)
        results: list[tuple[int, float]] = []

        with self._lock:
            for namespace in dict.fromkeys(namespaces):
                index = self._get(namespace)

                if index.ntotal == 0:
                    continue

                scores, labels = index.search(query, min(k, index.ntotal))

                for score, label in zip(scores[0], labels[0]):
                    if label != -1:
                        results.append((int(label), float(score)))

        results.sort(key=lambda item: item[1], reverse=True)
        return results[:k]

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                namespace: index.ntotal
                for namespace, index in self._indexes.items()
            }

    def _get(self, namespace: str) -> faiss.IndexIDMap2:
        cached = self._indexes.get(namespace)

        if cached is not None:
            return cached

        path = self.path_for(namespace)

        if path.exists():
            index = faiss.read_index(str(path))

            if index.d != self._dimensions:
                raise RuntimeError(
                    f"Index for namespace {namespace!r} has dimension "
                    f"{index.d}, but the configured embeddings dimension is "
                    f"{self._dimensions}. Re-ingest after removing "
                    f"{path}."
                )
        else:
            index = faiss.IndexIDMap2(faiss.IndexFlatIP(self._dimensions))

        self._indexes[namespace] = index
        return index

    def _add(
        self,
        index: faiss.IndexIDMap2,
        ids: Sequence[int],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        array = np.asarray(vectors, dtype="float32")

        if array.ndim != 2 or array.shape[1] != self._dimensions:
            raise ValueError(
                "vectors must be a 2-D array with "
                f"{self._dimensions} columns"
            )

        faiss.normalize_L2(array)
        index.add_with_ids(array, _as_ids(ids))

    def _save(self, namespace: str) -> None:
        path = self.path_for(namespace)
        temporary = path.with_name(path.name + ".tmp")
        faiss.write_index(self._indexes[namespace], str(temporary))
        os.replace(temporary, path)

    def _drop(self, namespace: str) -> None:
        self._indexes.pop(namespace, None)
        path = self.path_for(namespace)

        if path.exists():
            path.unlink()


def _as_ids(ids: Sequence[int]) -> np.ndarray:
    return np.asarray(list(ids), dtype="int64")


def _filename(namespace: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", namespace.lower()).strip("-")[:40] or "ns"
    digest = hashlib.sha1(namespace.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}.faiss"
