"""Ingestion and retrieval over local documents."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from agentic_chatbot.bm25_store import BM25IndexStore
from agentic_chatbot.loaders import (
    PDF_SUFFIXES,
    SUPPORTED_SUFFIXES,
    DocumentLoadError,
    load_file,
)
from agentic_chatbot.models import Chunk, Document, DocumentHit
from agentic_chatbot.pg_vector_store import PgVectorStore
from agentic_chatbot.repository import DocumentsRepository
from agentic_chatbot.rrf import reciprocal_rank_fusion

_LOGGER = logging.getLogger(__name__)

SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules"}
SEARCH_MODES = ("hybrid", "vector", "bm25")

_SEPARATORS = ["\n## ", "\n### ", "\n\n", "\n", ". ", " "]
_EMBED_BATCH = 64
_MAX_TOP_K = 10

# Filtering a ranking down to one owner's chunks can shrink a candidate list
# below the requested Top-K, so owner-scoped queries ask each retriever for
# proportionally more. The cap keeps a pathological over-fetch bounded.
_OWNER_OVERFETCH = 4
_MAX_OWNER_CANDIDATES = 100


class RetrievalError(Exception):
    """Raised when no retriever could produce results for a query."""


@dataclass
class IngestResult:
    files_seen: int = 0
    files_indexed: int = 0
    files_skipped: int = 0
    chunks_created: int = 0
    namespaces: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DocumentService:
    def __init__(
        self,
        repository: DocumentsRepository,
        vector_store: PgVectorStore,
        embeddings: Embeddings,
        *,
        chunk_size: int,
        chunk_overlap: int,
        default_namespace: str = "default",
        top_k: int = 4,
        min_score: float = 0.15,
        max_text_bytes: int = 2_000_000,
        max_pdf_bytes: int = 20_000_000,
        max_pdf_pages: int = 200,
        bm25_store: BM25IndexStore | None = None,
        search_mode: str = "vector",
        vector_candidates: int = 10,
        bm25_candidates: int = 10,
        rrf_k: int = 60,
    ):
        if search_mode not in SEARCH_MODES:
            raise ValueError(
                f"search_mode must be one of {SEARCH_MODES}, got {search_mode!r}"
            )

        self._repository = repository
        self._vector_store = vector_store
        self._embeddings = embeddings
        self._bm25_store = bm25_store or BM25IndexStore(repository)
        self._default_namespace = default_namespace
        self._top_k = top_k
        self._min_score = min_score
        self._max_text_bytes = max_text_bytes
        self._max_pdf_bytes = max_pdf_bytes
        self._max_pdf_pages = max_pdf_pages
        self._search_mode = search_mode
        self._vector_candidates = max(1, vector_candidates)
        self._bm25_candidates = max(1, bm25_candidates)
        self._rrf_k = rrf_k
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=_SEPARATORS,
        )

    def ingest_path(
        self,
        path: Path,
        namespace: str | None = None,
        force: bool = False,
        owner_id: str | None = None,
    ) -> IngestResult:
        namespace = self._namespace(namespace)
        path = Path(path)
        result = IngestResult()

        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = sorted(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and self._wanted(candidate)
            )
        else:
            result.errors.append((str(path), "path not found"))
            return result

        for file in files:
            result.files_seen += 1

            try:
                chunks_created, skipped, warning = self.ingest_file(
                    file, namespace, force=force, owner_id=owner_id
                )
            except DocumentLoadError as exc:
                result.errors.append((self._source(file), str(exc)))
                continue
            except Exception as exc:
                result.errors.append((self._source(file), str(exc)))
                continue

            if warning:
                result.warnings.append(warning)

            if skipped:
                result.files_skipped += 1
            else:
                result.files_indexed += 1
                result.chunks_created += chunks_created
                result.namespaces = [namespace]

        return result

    def ingest_file(
        self,
        path: Path,
        namespace: str,
        force: bool = False,
        owner_id: str | None = None,
    ) -> tuple[int, bool, str | None]:
        """Index one file.

        Returns ``(chunks_created, skipped, warning)``. Raises
        ``DocumentLoadError`` for unreadable or unsupported input.
        """
        namespace = self._namespace(namespace)
        path = Path(path)

        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise DocumentLoadError(
                f"unsupported file type: {path.suffix.lower() or '(none)'}"
            )

        try:
            size_bytes = path.stat().st_size
        except OSError as exc:
            raise DocumentLoadError(str(exc)) from exc

        limit = (
            self._max_pdf_bytes
            if path.suffix.lower() in PDF_SUFFIXES
            else self._max_text_bytes
        )

        if size_bytes > limit:
            raise DocumentLoadError(
                f"file is {size_bytes} bytes; limit is {limit}"
            )

        loaded = load_file(path, max_pdf_pages=self._max_pdf_pages)
        source = self._source(path)
        text = "\n\n".join(section.text for section in loaded.sections)
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        existing = self._repository.find_by_source(namespace, source)

        if existing and existing.content_hash == content_hash and not force:
            return 0, True, None

        chunks = [
            Chunk(content=piece, page=section.page)
            for section in loaded.sections
            for piece in self._splitter.split_text(section.text)
            if piece.strip()
        ]

        if not chunks:
            raise DocumentLoadError("no text chunks produced")

        vectors = self._embed([chunk.content for chunk in chunks])
        old_ids = (
            self._repository.chunk_ids(existing.doc_id) if existing else []
        )
        document, new_ids = self._repository.replace_document(
            namespace,
            source,
            path.stem,
            content_hash,
            size_bytes,
            chunks,
            owner_id=owner_id,
        )

        try:
            self._vector_store.replace(namespace, old_ids, new_ids, vectors)
        except Exception:
            self._repository.delete_document(document.doc_id)
            raise
        finally:
            # The stale check is fingerprint-based, but invalidating here keeps
            # the cache tight and avoids one needless rebuild after ingest.
            self._bm25_store.invalidate(namespace)

        warning = None

        if loaded.truncated:
            warning = f"{source}: truncated to {self._max_pdf_pages} pages"

        return len(chunks), False, warning

    def search(
        self,
        query: str,
        namespace: str | None = None,
        k: int | None = None,
        owner_id: str | None = None,
    ) -> list[DocumentHit]:
        """Retrieve chunks using the configured search mode.

        ``owner_id`` scopes retrieval to that user's documents. The filter runs
        inside both retrievers, before fusion, so a foreign chunk can neither be
        returned nor influence the order of an authorized one. ``None`` keeps the
        CLI's global behaviour.
        """
        if not query.strip():
            return []

        limit = self._clamp_k(k)
        namespaces = self._search_namespaces(namespace, owner_id)

        if not namespaces:
            return []

        allowed = self._allowed_ids(owner_id, namespaces)
        candidates = self._candidates(limit, allowed is not None)
        mode = self._search_mode

        if mode == "vector":
            ranked, vector_scores = self._rank_vector(
                query, namespaces, candidates, allowed
            )
            return self._build_hits(
                ranked[:limit],
                vector_scores,
                None,
                filter_min_score=True,
            )

        if mode == "bm25":
            ranked, bm25_scores = self._rank_bm25(
                query, namespaces, candidates, allowed
            )
            return self._build_hits(ranked[:limit], None, bm25_scores)

        return self._hybrid_search(query, namespaces, limit, allowed=allowed)

    def search_vector(
        self,
        query: str,
        namespace: str | None = None,
        k: int | None = None,
        owner_id: str | None = None,
    ) -> list[DocumentHit]:
        """FAISS semantic search only, independent of the configured mode."""
        if not query.strip():
            return []

        namespaces = self._search_namespaces(namespace, owner_id)

        if not namespaces:
            return []

        limit = self._clamp_k(k)
        allowed = self._allowed_ids(owner_id, namespaces)
        candidates = self._candidates(limit, allowed is not None)
        ranked, vector_scores = self._rank_vector(
            query, namespaces, candidates, allowed
        )
        return self._build_hits(
            ranked[:limit], vector_scores, None, filter_min_score=True
        )

    def search_bm25(
        self,
        query: str,
        namespace: str | None = None,
        k: int | None = None,
        owner_id: str | None = None,
    ) -> list[DocumentHit]:
        """BM25 keyword search only, with no embedding call."""
        if not query.strip():
            return []

        namespaces = self._search_namespaces(namespace, owner_id)

        if not namespaces:
            return []

        limit = self._clamp_k(k)
        allowed = self._allowed_ids(owner_id, namespaces)
        candidates = self._candidates(limit, allowed is not None)
        ranked, bm25_scores = self._rank_bm25(
            query, namespaces, candidates, allowed
        )
        return self._build_hits(ranked[:limit], None, bm25_scores)

    def search_hybrid(
        self,
        query: str,
        namespace: str | None = None,
        k: int | None = None,
        owner_id: str | None = None,
    ) -> list[DocumentHit]:
        """Vector + BM25 fusion with RRF, independent of the configured mode."""
        if not query.strip():
            return []

        namespaces = self._search_namespaces(namespace, owner_id)

        if not namespaces:
            return []

        allowed = self._allowed_ids(owner_id, namespaces)
        return self._hybrid_search(
            query, namespaces, self._clamp_k(k), allowed=allowed
        )

    def _hybrid_search(
        self,
        query: str,
        namespaces: Sequence[str],
        limit: int,
        allowed: set[int] | None = None,
    ) -> list[DocumentHit]:
        """Run both retrievers concurrently and fuse their rankings with RRF.

        The retrievers are blocking and thread-safe, so a two-worker thread pool
        gives real overlap without making the service asynchronous. A failure in
        one retriever is logged and the other still contributes, except when
        both fail, which is surfaced instead of silently returning nothing.

        ``allowed`` restricts each ranking before fusion; see ``search``.
        """
        vector_candidates = (
            self._candidates(self._vector_candidates, allowed is not None)
            if allowed is not None
            else self._vector_candidates
        )
        bm25_candidates = (
            self._candidates(self._bm25_candidates, allowed is not None)
            if allowed is not None
            else self._bm25_candidates
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            vector_future = executor.submit(
                self._rank_vector,
                query,
                namespaces,
                vector_candidates,
                allowed,
                True,
            )
            bm25_future = executor.submit(
                self._rank_bm25,
                query,
                namespaces,
                bm25_candidates,
                allowed,
                True,
            )

        vector_result = _settle(vector_future, "vector")
        bm25_result = _settle(bm25_future, "bm25")

        if vector_result is None and bm25_result is None:
            raise RetrievalError("both vector and BM25 retrieval failed")

        vector_ids, vector_scores = _split(vector_result)
        bm25_ids, bm25_scores = _split(bm25_result)
        fused = reciprocal_rank_fusion(
            [vector_ids, bm25_ids], k=self._rrf_k, limit=limit
        )

        if not fused:
            return []

        _LOGGER.debug(
            "hybrid search: %d vector, %d bm25 candidates -> %d fused",
            len(vector_ids),
            len(bm25_ids),
            len(fused),
        )

        return self._build_hits(
            [row_id for row_id, _ in fused],
            vector_scores,
            bm25_scores,
            scores=dict(fused),
        )

    def _rank_vector(
        self,
        query: str,
        namespaces: Sequence[str],
        candidates: int,
        allowed: set[int] | None,
        allow_failure: bool = False,
    ) -> tuple[list[int], dict[int, float]] | None:
        """Rank by vector similarity, then drop ids the caller may not read.

        Filtering happens on the ranking itself so an unauthorized chunk is
        never fused, never joined, and never reaches the model.
        """
        ranking = self._retrieve_vector(
            query, namespaces, candidates, allow_failure
        )

        if ranking is None or allowed is None:
            return ranking

        ids, scores = ranking
        kept = [row_id for row_id in ids if row_id in allowed]

        return kept, {row_id: scores[row_id] for row_id in kept}

    def _rank_bm25(
        self,
        query: str,
        namespaces: Sequence[str],
        candidates: int,
        allowed: set[int] | None,
        allow_failure: bool = False,
    ) -> tuple[list[int], dict[int, float]] | None:
        """Rank by BM25, then drop ids the caller may not read."""
        ranking = self._retrieve_bm25(
            query, namespaces, candidates, allow_failure
        )

        if ranking is None or allowed is None:
            return ranking

        ids, scores = ranking
        kept = [row_id for row_id in ids if row_id in allowed]

        return kept, {row_id: scores[row_id] for row_id in kept}

    def _retrieve_vector(
        self,
        query: str,
        namespaces: Sequence[str],
        candidates: int,
        allow_failure: bool = False,
    ) -> tuple[list[int], dict[int, float]] | None:
        """Return ordered vector-ranked ids plus a ``row_id -> similarity`` map."""
        try:
            vector = self._embeddings.embed_query(query)
            hits = self._vector_store.search(namespaces, vector, candidates)
        except Exception:
            if not allow_failure:
                raise

            _LOGGER.exception("vector retrieval failed; fusing BM25 only")
            return None

        return [row_id for row_id, _ in hits], dict(hits)

    def _retrieve_bm25(
        self,
        query: str,
        namespaces: Sequence[str],
        candidates: int,
        allow_failure: bool = False,
    ) -> tuple[list[int], dict[int, float]] | None:
        """Return ordered BM25-ranked ids plus a ``row_id -> score`` map."""
        try:
            hits = self._bm25_store.search(namespaces, query, candidates)
        except Exception:
            if not allow_failure:
                raise

            _LOGGER.exception("BM25 retrieval failed; fusing vector only")
            return None

        return [row_id for row_id, _ in hits], dict(hits)


    def _build_hits(
        self,
        ranked: Sequence[int],
        vector_scores: dict[int, float] | None,
        bm25_scores: dict[int, float] | None,
        *,
        scores: dict[int, float] | None = None,
        filter_min_score: bool = False,
    ) -> list[DocumentHit]:
        """Join ranked row ids to SQLite rows and build ``DocumentHit``s.

        ``scores`` overrides the per-hit score (RRF fusion scores) keyed by row
        id; otherwise the best available retriever score is used.
        ``filter_min_score`` keeps the existing vector-only behaviour of dropping
        weak cosine matches.
        """
        if not ranked:
            return []

        rows = self._repository.chunks_by_ids(list(ranked))
        vector_scores = vector_scores or {}
        bm25_scores = bm25_scores or {}
        results: list[DocumentHit] = []

        for row_id in ranked:
            row = rows.get(row_id)

            if row is None:
                continue

            vector_score = vector_scores.get(row_id)
            bm25_score = bm25_scores.get(row_id)

            if scores is not None:
                score = float(scores[row_id])
            elif vector_score is not None:
                score = float(vector_score)
            elif bm25_score is not None:
                score = float(bm25_score)
            else:
                continue

            if filter_min_score and score < self._min_score:
                continue

            results.append(
                DocumentHit(
                    chunk_id=row["chunk_id"],
                    doc_id=row["doc_id"],
                    namespace=row["namespace"],
                    title=row["title"],
                    source=row["source"],
                    chunk_index=int(row["chunk_index"]),
                    page=row["page"],
                    content=row["content"],
                    score=score,
                    vector_score=vector_score,
                    bm25_score=bm25_score,
                )
            )

        return results

    def _search_namespaces(
        self, namespace: str | None, owner_id: str | None = None
    ) -> list[str]:
        requested = [self._namespace(namespace)] if namespace else None

        if owner_id is None:
            return requested or self._repository.list_namespaces()

        owned = self._repository.list_namespaces(owner_id=owner_id)

        if requested is None:
            return owned

        return [name for name in requested if name in owned]

    def _allowed_ids(
        self, owner_id: str | None, namespaces: Sequence[str]
    ) -> set[int] | None:
        """Row ids the caller may retrieve, or ``None`` for no restriction."""
        if owner_id is None:
            return None

        return self._repository.authorized_chunk_ids(owner_id, namespaces)

    def _candidates(self, wanted: int, restricted: bool) -> int:
        """Ask for more candidates when a later ownership filter will trim them."""
        if not restricted:
            return wanted

        return min(_MAX_OWNER_CANDIDATES, max(wanted, wanted * _OWNER_OVERFETCH))

    def list_documents(
        self, namespace: str | None = None, owner_id: str | None = None
    ) -> list[Document]:
        return self._repository.list_documents(namespace, owner_id=owner_id)

    def get_document(self, doc_id: str) -> Document | None:
        return self._repository.get(doc_id)

    def find_document(self, namespace: str | None, path: Path) -> Document | None:
        """Resolve the document an ingested file became.

        ``ingest_file`` names documents after the file stem and keys them by
        ``(namespace, source)``, so this is the reliable way back to the row
        after ingestion — unlike matching on the title.
        """
        return self._repository.find_by_source(
            self._namespace(namespace), self._source(Path(path))
        )

    def list_namespaces(self, owner_id: str | None = None) -> list[str]:
        return self._repository.list_namespaces(owner_id=owner_id)

    def delete_document(self, doc_id: str) -> bool:
        document = self._repository.get(doc_id)

        if document is None:
            return False

        row_ids = self._repository.chunk_ids(doc_id)
        deleted = self._repository.delete_document(doc_id)

        if deleted:
            self._vector_store.remove(document.namespace, row_ids)
            self._bm25_store.invalidate(document.namespace)

        return deleted

    def stats(self) -> dict:
        stats = self._repository.stats()
        stats["indexes"] = self._vector_store.stats()
        stats["bm25_indexes"] = self._bm25_store.stats()
        return stats

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []

        for start in range(0, len(texts), _EMBED_BATCH):
            batch = list(texts[start : start + _EMBED_BATCH])
            vectors.extend(self._embeddings.embed_documents(batch))

        return vectors

    def _clamp_k(self, k: int | None) -> int:
        value = self._top_k if k is None else int(k)
        return max(1, min(_MAX_TOP_K, value))

    def _namespace(self, namespace: str | None) -> str:
        return (namespace or "").strip()[:64] or self._default_namespace

    def _wanted(self, path: Path) -> bool:
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            return False

        if path.name.startswith("."):
            return False

        return not any(part in SKIP_DIRS for part in path.parts)

    def _source(self, path: Path) -> str:
        resolved = path.resolve()

        try:
            return resolved.relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            return resolved.as_posix()


def _settle(
    future,
    label: str,
) -> tuple[list[int], dict[int, float]] | None:
    """Collect a retriever result, logging a failure instead of propagating it."""
    try:
        return future.result()
    except Exception:
        _LOGGER.exception("%s retrieval raised unexpectedly", label)
        return None


def _split(
    result: tuple[list[int], dict[int, float]] | None,
) -> tuple[list[int], dict[int, float]]:
    if result is None:
        return [], {}

    return result
