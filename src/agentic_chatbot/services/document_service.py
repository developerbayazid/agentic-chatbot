"""Ingestion and retrieval over local documents."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from agentic_chatbot.loaders import (
    PDF_SUFFIXES,
    SUPPORTED_SUFFIXES,
    DocumentLoadError,
    load_file,
)
from agentic_chatbot.models import Chunk, Document, DocumentHit
from agentic_chatbot.repository import DocumentsRepository
from agentic_chatbot.vector_store import VectorIndexStore

SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules"}

_SEPARATORS = ["\n## ", "\n### ", "\n\n", "\n", ". ", " "]
_EMBED_BATCH = 64
_MAX_TOP_K = 10


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
        vector_store: VectorIndexStore,
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
    ):
        self._repository = repository
        self._vector_store = vector_store
        self._embeddings = embeddings
        self._default_namespace = default_namespace
        self._top_k = top_k
        self._min_score = min_score
        self._max_text_bytes = max_text_bytes
        self._max_pdf_bytes = max_pdf_bytes
        self._max_pdf_pages = max_pdf_pages
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
                    file, namespace, force=force
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
        )

        try:
            self._vector_store.replace(namespace, old_ids, new_ids, vectors)
        except Exception:
            self._repository.delete_document(document.doc_id)
            raise

        warning = None

        if loaded.truncated:
            warning = f"{source}: truncated to {self._max_pdf_pages} pages"

        return len(chunks), False, warning

    def search(
        self,
        query: str,
        namespace: str | None = None,
        k: int | None = None,
    ) -> list[DocumentHit]:
        if not query.strip():
            return []

        limit = self._clamp_k(k)
        vector = self._embeddings.embed_query(query)

        if namespace:
            namespaces = [self._namespace(namespace)]
        else:
            namespaces = self._repository.list_namespaces()

        hits = self._vector_store.search(namespaces, vector, limit)

        if not hits:
            return []

        rows = self._repository.chunks_by_ids([row_id for row_id, _ in hits])
        results: list[DocumentHit] = []

        for row_id, score in hits:
            row = rows.get(row_id)

            if row is None or score < self._min_score:
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
                )
            )

        return results

    def list_documents(self, namespace: str | None = None) -> list[Document]:
        return self._repository.list_documents(namespace)

    def list_namespaces(self) -> list[str]:
        return self._repository.list_namespaces()

    def delete_document(self, doc_id: str) -> bool:
        document = self._repository.get(doc_id)

        if document is None:
            return False

        row_ids = self._repository.chunk_ids(doc_id)
        deleted = self._repository.delete_document(doc_id)

        if deleted:
            self._vector_store.remove(document.namespace, row_ids)

        return deleted

    def stats(self) -> dict:
        stats = self._repository.stats()
        stats["indexes"] = self._vector_store.stats()
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
