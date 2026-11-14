# Plan: RAG with FAISS, one index per namespace (text + PDF)

## Goal

Add retrieval-augmented generation to the existing CLI chatbot using **FAISS** as
the vector store, with **one FAISS index file per namespace**:

- Documents live in `docs/` (or any path), are loaded from **Markdown, plain
  text, reStructuredText, and PDF**, chunked, embedded with OpenAI
  `text-embedding-3-small`, and their **text/metadata** is stored in the existing
  `chatbot_memory.db`; their **vectors** live in per-namespace FAISS indexes under
  `data/faiss/`.
- Every document belongs to a namespace (default `default`). A search can be
  scoped to one namespace or run across all of them (merge per-index results).
- PDF chunks carry their **page number**, so answers can cite page ranges.
- The model reaches the knowledge base through a **retriever tool**
  (`search_documents`) in the existing tool registry, so **the LangGraph
  workflow does not change**.
- `/ingest` indexes a folder or file; `/documents` shows what is indexed.

Decisions already made: retriever tool (not an auto-inject node), namespaced KB,
`docs/` + `/ingest` ingestion, OpenAI embeddings, FAISS with per-namespace
indexes, PDF support.

### Why this fits the current architecture

The project already hand-writes repositories over one SQLite connection; FAISS
becomes one more storage adapter behind a small class, with SQLite holding the
authoritative chunk text. No second database, no native server, and no
`langchain-community` vectorstore wrapper.

Dependency checks (`uv pip install --dry-run` for this interpreter):

- **faiss-cpu 1.16.0** — available.
- **pypdf 7.1.0** — available, pure Python, no native build.

Dependency flow stays one-way:

```
cli/ → container → services/document_service → repository → database.py
                                          └→ vector_store.py (FAISS)
                                          └→ loaders.py (text/PDF)
                                          └→ tools/documents.py → registry
```

`graph/` and `services/chat_service.py` are untouched.

---

## 1. Dependencies

`pyproject.toml` — add:

```toml
"faiss-cpu>=1.16.0",
"numpy>=2",
"pypdf>=7.1.0",
"langchain-text-splitters>=1.0",
```

Then `uv sync`. `pypdf` is the extractor; **no OCR** (scanned/image-only PDFs are
reported as errors, see Section 4).

`numpy` is declared explicitly even though it is currently transitive — the
vector store imports it directly.

---

## 2. Configuration — `src/agentic_chatbot/config.py`

Add to `Settings`:

| Setting                | Env var                | Default                   |
| ---------------------- | ---------------------- | ------------------------- |
| `embeddings_model`     | `EMBEDDINGS_MODEL`     | `text-embedding-3-small`  |
| `embedding_dimensions` | `EMBEDDING_DIMENSIONS` | `1536`                    |
| `rag_chunk_size`       | `RAG_CHUNK_SIZE`       | `800`                     |
| `rag_chunk_overlap`    | `RAG_CHUNK_OVERLAP`    | `120`                     |
| `rag_top_k`            | `RAG_TOP_K`            | `4`                       |
| `docs_path`            | `DOCS_PATH`            | `docs`                    |
| `rag_index_path`       | `RAG_INDEX_PATH`       | `data/faiss`              |
| `rag_max_text_bytes`   | `RAG_MAX_TEXT_BYTES`   | `2000000`                 |
| `rag_max_pdf_bytes`    | `RAG_MAX_PDF_BYTES`    | `20000000`                |
| `rag_max_pdf_pages`    | `RAG_MAX_PDF_PAGES`    | `200`                     |

No behaviour change for existing settings.

---

## 3. Embeddings factory — `src/agentic_chatbot/embeddings.py` (new)

Mirror `llm.py` so a future provider swap is a one-file change:

```python
from langchain_openai import OpenAIEmbeddings

def create_embeddings(settings, dimensions=None) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embeddings_model,
        api_key=settings.openai_api_key,
        dimensions=dimensions or settings.embedding_dimensions,
    )
```

Constructing it makes **no network call** — safe at container startup.

---

## 4. Loaders — `src/agentic_chatbot/loaders.py` (new)

One module owns "file → text sections". It keeps PDF quirks out of the service
and is directly unit-testable.

```python
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst"}
PDF_SUFFIXES = {".pdf"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | PDF_SUFFIXES

class DocumentLoadError(Exception):
    """Raised when a file cannot be turned into text."""

@dataclass(frozen=True)
class Section:
    page: int | None      # 1-based PDF page, None for plain-text files
    text: str

@dataclass(frozen=True)
class LoadResult:
    sections: list[Section]
    truncated: bool = False

def load_file(path: Path, *, max_pdf_pages: int = 200) -> LoadResult: ...
```

Behaviour:

- Dispatch on `path.suffix.lower()`; an unsupported suffix raises
  `DocumentLoadError`.
- Text files: one section, `page=None`, read with
  `path.read_text(encoding="utf-8", errors="replace")`.
- PDFs:

```python
from pypdf import PdfReader

reader = PdfReader(str(path))
if reader.is_encrypted and not reader.decrypt(""):
    raise DocumentLoadError("encrypted PDF; decrypt it before ingesting")

sections: list[Section] = []
truncated = False

for number, page in enumerate(reader.pages, start=1):
    if number > max_pdf_pages:
        truncated = True
        break
    try:
        text = page.extract_text() or ""
    except Exception as exc:
        raise DocumentLoadError(f"page {number}: {exc}") from exc
    text = _normalize(text)
    if text:
        sections.append(Section(page=number, text=text))

if not sections:
    raise DocumentLoadError(
        "no extractable text (scanned PDF? OCR is not supported)"
    )

return LoadResult(sections=sections, truncated=truncated)
```

- `_normalize(text)`: strip NULs, normalize CRLF to LF, collapse runs of 3+
  newlines to 2, strip leading/trailing whitespace.
- Pages with no text (image-only) are skipped; if **every** page is empty the
  whole file is an error, because there is nothing to embed.
- `pypdf.PdfReader` is imported at module top; it is a declared dependency.

PDF chunks are produced **per page**, so a chunk never spans a page boundary and
page citations stay accurate.

---

## 5. Schema — `src/agentic_chatbot/database.py`

No SQLite extension is needed. SQLite owns text and metadata only; FAISS owns
vectors.

```python
DOCUMENTS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT PRIMARY KEY,
    namespace    TEXT NOT NULL,
    source       TEXT NOT NULL,
    title        TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (namespace, source)
)
"""

DOCUMENT_CHUNKS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS document_chunks (
    row_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id    TEXT NOT NULL UNIQUE,
    doc_id      TEXT NOT NULL,
    namespace   TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page        INTEGER,
    content     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

DOCUMENT_CHUNKS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks (doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_namespace ON document_chunks (namespace);
"""

RAG_META_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS rag_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""
```

`document_chunks.row_id` is the FAISS vector id. It is an
`INTEGER PRIMARY KEY AUTOINCREMENT`, so it is globally unique and stable across
restarts; a FAISS index therefore stores only `(row_id, vector)` and every
result joins straight back to SQLite. `page` is `NULL` for text files.

`init_schema` gains the three statements plus a dimension guard:

```python
def init_schema(connection, *, embedding_dimensions: int = 1536) -> None:
    ...existing threads/notes work...
    connection.execute(DOCUMENTS_TABLE_SCHEMA)
    connection.execute(DOCUMENT_CHUNKS_TABLE_SCHEMA)
    connection.executescript(DOCUMENT_CHUNKS_INDEXES)
    connection.execute(RAG_META_TABLE_SCHEMA)
    _check_embedding_dimensions(connection, embedding_dimensions)
    connection.commit()
```

`_check_embedding_dimensions` records `embedding_dimensions` and
`index_format_version = 1` in `rag_meta` on first run; if a later run sees a
different value it raises a `RuntimeError` explaining that the SQLite rows and
the FAISS files must be cleared and re-ingested. This prevents mixing vector
sizes.

`container.py` passes `embedding_dimensions=settings.embedding_dimensions`.

---

## 6. Models — `src/agentic_chatbot/models.py`

Add frozen dataclasses next to `Note`:

```python
@dataclass(frozen=True)
class Chunk:
    content: str
    page: int | None = None

@dataclass(frozen=True)
class Document:
    doc_id: str
    namespace: str
    source: str
    title: str
    content_hash: str
    size_bytes: int
    created_at: str | None
    updated_at: str | None

@dataclass(frozen=True)
class DocumentHit:
    chunk_id: str
    doc_id: str
    namespace: str
    title: str
    source: str
    chunk_index: int
    page: int | None
    content: str
    score: float          # cosine similarity: HIGHER is better
```

`Chunk` is the repository/service boundary: text plus optional page provenance.
`score` replaces a distance field: FAISS `IndexFlatIP` returns inner product, and
vectors are L2-normalized, so the score is cosine similarity in `[-1, 1]`.

`TurnEvent` is unchanged.

---

## 7. Repository — `src/agentic_chatbot/repository.py`

Add `DocumentsRepository` (owns **all** SQL for the new tables; no vector logic):

| Method | Behaviour |
| --- | --- |
| `get(doc_id)` | one `Document` |
| `find_by_source(namespace, source)` | dedupe lookup |
| `list_documents(namespace=None)` | ordered by `namespace, source` |
| `list_namespaces()` | `SELECT DISTINCT namespace ORDER BY namespace` |
| `replace_document(namespace, source, title, content_hash, size_bytes, chunks: Sequence[Chunk]) -> tuple[Document, list[int]]` | one transaction: upsert `documents`, delete old chunks, insert new chunks (with `page`); returns the document and the new chunk `row_id`s in `chunk_index` order |
| `chunk_ids(doc_id) -> list[int]` | existing vector ids, read **before** a replace |
| `chunks_by_ids(ids)` | `SELECT` chunk rows joined to `documents` (including `page`), returned as a dict `row_id -> row` |
| `delete_document(doc_id) -> bool` | delete chunks, then the document row |
| `stats()` | `{documents, chunks, namespaces}` |

No embeddings or FAISS imports live here.

---

## 8. Vector store — `src/agentic_chatbot/vector_store.py` (new)

`VectorIndexStore` — one FAISS index per namespace, persisted to disk.

```python
import faiss
import numpy as np

class VectorIndexStore:
    def __init__(self, directory: Path, dimensions: int): ...
    def add(self, namespace: str, ids: Sequence[int], vectors) -> None
    def replace(self, namespace: str, remove_ids: Sequence[int],
                add_ids: Sequence[int], vectors) -> None
    def remove(self, namespace: str, ids: Sequence[int]) -> None
    def search(self, namespaces: Sequence[str], vector, k: int) -> list[tuple[int, float]]
    def stats(self) -> dict[str, int]
```

### Index shape

- `faiss.IndexIDMap2(faiss.IndexFlatIP(dimensions))` — flat index with explicit
  int64 ids (`document_chunks.row_id`); normalized vectors ⇒ cosine similarity.
- One `.faiss` file per namespace. Filename must be filesystem-safe and
  collision-free:

```python
def _filename(namespace: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", namespace.lower()).strip("-")[:40] or "ns"
    digest = hashlib.sha1(namespace.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}.faiss"
```

- Default directory `settings.rag_index_path`, created with
  `mkdir(parents=True, exist_ok=True)`.

### Lifecycle

- Lazy load: the first use of a namespace reads its file with
  `faiss.read_index`; a missing file yields a fresh empty index. Loaded indexes
  are cached in a dict.
- Dimension guard on load: `index.d != self._dimensions` raises a `RuntimeError`
  naming the namespace and telling the user to re-ingest (changing
  `EMBEDDINGS_MODEL` or `EMBEDDING_DIMENSIONS` invalidates every index).
- Writes are atomic: `faiss.write_index(index, tmp)` then `os.replace(tmp, path)`.
- `replace()` removes old ids, adds new ids, and saves **once**.
- `remove()` deletes the index file and cache entry when `index.ntotal == 0`.
- A `threading.Lock` guards load/save so a future FastAPI layer cannot corrupt
  files mid-write.
- `search()`: the candidate namespace list comes from the caller (the service
  reads `DocumentsRepository.list_namespaces()`), queries each index, drops `-1`
  labels for empty slots, then merges and truncates to `k`. Cross-namespace
  search is a merge of per-index results — correct, just not one global index.

Vectors are normalized with `faiss.normalize_L2` on write and on query, so scores
are well-defined regardless of provider normalization.

---

## 9. Service — `src/agentic_chatbot/services/document_service.py` (new)

```python
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules"}

class DocumentService:
    def __init__(self, repository, vector_store, embeddings, *,
                 chunk_size, chunk_overlap, default_namespace="default",
                 top_k=4, max_text_bytes=2_000_000,
                 max_pdf_bytes=20_000_000, max_pdf_pages=200): ...

    def ingest_path(self, path: Path, namespace: str | None = None,
                    force: bool = False) -> IngestResult
    def ingest_file(self, path: Path, namespace: str, force: bool = False) -> None
    def search(self, query: str, namespace: str | None = None,
               k: int | None = None) -> list[DocumentHit]
    def list_documents(self, namespace: str | None = None) -> list[Document]
    def list_namespaces(self) -> list[str]
    def delete_document(self, doc_id: str) -> bool
    def stats(self) -> dict
```

`IngestResult` is a frozen dataclass local to this module:
`files_seen, files_indexed, files_skipped, chunks_created, namespaces, errors,
warnings`
(`errors: list[tuple[str, str]]` of `(path, message)`;
`warnings: list[str]` for truncation and other non-fatal notes).

Rules:

- `ingest_path`: file ⇒ ingest it; directory ⇒ `rglob("*")` skipping `SKIP_DIRS`,
  hidden entries, and unsupported suffixes. A missing path returns an
  `IngestResult` with one error — never raises.
- Supported suffixes come from `loaders.SUPPORTED_SUFFIXES`
  (`.md`, `.markdown`, `.txt`, `.rst`, `.pdf`).
- Size limits per file: `max_text_bytes` for text files, `max_pdf_bytes` for
  PDFs. Oversized files are recorded in `errors` and skipped.
- Namespace defaults to `default`, stripped, truncated to 64 chars, `default`
  when empty.
- **Loading:** `result = load_file(path, max_pdf_pages=max_pdf_pages)`.
  `DocumentLoadError` (unsupported, encrypted, scanned, corrupt) is recorded in
  `errors` per file; ingestion continues. If `result.truncated`, append
  `"<source>: truncated to N pages"` to `warnings`.
- Dedupe: `sha256` of the concatenated section text. Same `(namespace, source)`
  and same hash ⇒ `files_skipped += 1` and **no embedding call**, unless
  `force=True` (used to rebuild an index after `data/faiss/` is lost).
- Chunking: `RecursiveCharacterTextSplitter` with `chunk_size`, `chunk_overlap`,
  separators `["\n## ", "\n### ", "\n\n", "\n", ". ", " "]`. **Each section is
  chunked independently**, and every produced `Chunk` inherits `section.page`,
  so PDF provenance survives chunking. Empty chunks are dropped.
- Embedding: `embeddings.embed_documents(texts)` in batches of 64.
- **Write order per file** (keeps SQLite and FAISS consistent):
  1. `old_ids = repository.chunk_ids(existing_doc_id)` when replacing;
  2. embed the new chunks;
  3. `document, new_ids = repository.replace_document(...)` (SQL transaction);
  4. `vector_store.replace(namespace, old_ids, new_ids, vectors)` (one save);
  5. if step 4 raises, compensate with `repository.delete_document(document.doc_id)`
     and record the file error, so an orphaned SQL row cannot outlive a failed
     index write.
- `search`: blank query ⇒ `[]`; clamp `k` to `1..10` (default `top_k`); embed the
  query; choose the namespaces (`[namespace]`, or all from the repository); call
  `vector_store.search(namespaces, vector, k)`; fetch rows with
  `repository.chunks_by_ids(...)`; build `DocumentHit`s **preserving score
  order** (ids returned out of order must not reshuffle results).
- `delete_document`: read `chunk_ids`, delete SQL rows, then
  `vector_store.remove(document.namespace, ids)`.

Export `DocumentService` from `services/__init__.py`.

---

## 10. Tool — `src/agentic_chatbot/tools/documents.py` (new)

Factory closing over the service, matching `create_note_tools`:

```python
def create_document_tools(service: DocumentService) -> list[BaseTool]:
```

- `search_documents(query: str, namespace: str = "", k: int = 4) -> str`
  - Docstring (model-facing): search the ingested knowledge base (Markdown,
    text, and PDF documents); use it for questions about the user's
    documents/handbooks/specs; leave `namespace` empty to search every
    namespace, or pass one reported by `list_documents`; cite the source and, for
    PDFs, the page.
  - Returns JSON: `{"query", "namespace", "count", "results": [{title, source,
    namespace, chunk_index, page, score, content}]}`.
  - `"Error: query is required."` for blank input; a friendly
    `"No matching documents..."` payload when there are no hits. Never raises.
- `list_documents(namespace: str = "") -> str`
  - Returns `{"namespaces": [...], "count": n, "documents": [{doc_id, title,
    source, namespace, size_bytes, updated_at}]}`.

Errors are strings, exactly like the notes tools, so the model can recover.

---

## 11. Registry — `src/agentic_chatbot/tools/registry.py`

```python
def get_tools(notes_repository, document_service=None) -> list[BaseTool]:
    tools = [*STATIC_TOOLS, *create_note_tools(notes_repository)]
    if document_service is not None:
        tools.extend(create_document_tools(document_service))
    return tools
```

Backwards compatible: one-argument callers still get 36 tools.

---

## 12. Container — `src/agentic_chatbot/container.py`

```python
self.embeddings = create_embeddings(settings)
self.documents_repository = DocumentsRepository(self.connection)
self.vector_store = VectorIndexStore(
    Path(settings.rag_index_path), settings.embedding_dimensions
)
self.document_service = DocumentService(
    self.documents_repository,
    self.vector_store,
    self.embeddings,
    chunk_size=settings.rag_chunk_size,
    chunk_overlap=settings.rag_chunk_overlap,
    top_k=settings.rag_top_k,
    max_text_bytes=settings.rag_max_text_bytes,
    max_pdf_bytes=settings.rag_max_pdf_bytes,
    max_pdf_pages=settings.rag_max_pdf_pages,
)
self.tools = get_tools(self.notes_repository, self.document_service)
```

Pass `embedding_dimensions=settings.embedding_dimensions` to `init_schema`.

Append a retrieval hint to the prompt `ChatService` receives:

```python
RAG_HINT = (
    "\n\nWhen a question could be answered by the user's ingested documents, "
    "call search_documents first and cite the document title and source "
    "(and page number for PDFs). If nothing is found, say so instead of guessing."
)
```

`ChatService(..., settings.system_prompt + RAG_HINT)`. The constant lives in
`container.py` so `Settings.system_prompt` semantics stay untouched.

---

## 13. CLI

### `src/agentic_chatbot/cli/session.py`

```python
@property
def document_service(self):
    return self.container.document_service
```

### `src/agentic_chatbot/cli/commands.py`

Two handlers plus their `Command` entries, category `CATEGORY_GENERAL` (no new
category, so `CATEGORY_ORDER`/console stay as-is):

- `/ingest [path] [namespace] [--force]`
  - Defaults: `path = session.settings.docs_path`, `namespace = "default"`.
  - Calls `session.document_service.ingest_path(Path(path), namespace, force=...)`.
  - Renders with `ui.document(console, "Ingested", ...)`: indexed/skipped/chunk
    counts and namespaces, a note when PDFs were truncated, and each error via
    `ui.warning`. Missing path ⇒ `ui.error`, never a crash.
  - `behavior`: "Chunks, embeds, and indexes Markdown, text, and PDF files."
- `/documents [namespace]`
  - Calls `list_documents` + `list_namespaces`; one row per document.
    Empty KB ⇒ `ui.notice`.

Both are picked up automatically by `/help`, completion, and the `/` menu.

---

## 14. Docs, env, gitignore

- `.env.example`: add the ten new variables with defaults.
- `.gitignore`: add `data/faiss/` and the verification DB `tmp_rag.db`.
- `docs/` is user-owned: add `docs/.gitkeep` only so the folder exists; do not
  commit sample content that would pollute retrieval.
- `ARCHITECTURE.md`: project layout (+ `embeddings.py`, `loaders.py`,
  `vector_store.py`, `services/document_service.py`, `tools/documents.py`),
  module reference entry, persistence section (two new tables + `rag_meta`, plus
  FAISS files), extension points, tool count 36 → 38, and a note that PDF text
  extraction uses `pypdf` without OCR.
- `README.md`: tech stack rows (FAISS + OpenAI embeddings + pypdf), tool table
  (+2), `/ingest` + `/documents` in the command table, supported file types,
  learning-progress checkbox.

---

## 15. Tests (all offline)

Add to `tests/fakes.py`:

```python
class FakeEmbeddings:
    """Deterministic, dependency-free Embeddings double."""
    def __init__(self, dimensions=8): ...
    def embed_documents(self, texts): return [self._vector(t) for t in texts]
    def embed_query(self, text): return self._vector(text)
    # _vector: hash tokens -> seeded floats, L2-normalized; same text -> same vector
```

New files:

- `tests/test_loaders.py` — text/markdown/rst load as one
  `Section(page=None)`; unsupported suffix raises `DocumentLoadError`;
  normalization collapses blank runs; PDF cases with `pypdf.PdfReader`
  monkeypatched: multiple pages → per-page sections with 1-based page numbers;
  an empty page is skipped; all-empty pages ⇒ `DocumentLoadError` (scanned);
  an encrypted PDF raises unless an empty password decrypts; `max_pdf_pages`
  sets `truncated=True`; a page whose `extract_text` raises becomes a
  `DocumentLoadError`. Plus one real smoke test writing a minimal single-page
  PDF with a helper (`_pdf_bytes(text)` building a valid xref) to prove pypdf is
  wired correctly end to end.
- `tests/test_vector_store.py` — add/search round trip; **one file per
  namespace** on disk; namespace isolation (a query hits only its own index);
  cross-namespace merge ordering; `replace` removes old ids and adds new ones;
  `remove` deletes the file when empty; persistence across store instances;
  dimension mismatch on load raises.
- `tests/test_documents_repository.py` — upsert/replace returns new row ids,
  `page` round-trips (`NULL` for text, int for PDF), `chunk_ids`,
  `chunks_by_ids`, delete, `list_namespaces`, `stats`, idempotent `init_schema`,
  dimension guard.
- `tests/test_document_service.py` — ingest file and tree; skip
  hidden/unsupported/oversized (text and PDF limits separately); a scanned PDF
  lands in `errors` while other files in the same tree still ingest; PDF chunks
  carry page numbers; dedupe by hash (assert `embed_documents` call count does
  not grow); `force` re-embeds unchanged files; re-ingest after content change
  replaces chunks and vector ids; namespace scoping and cross-namespace search;
  missing path returns an error result; `k` clamping; blank query; index-write
  failure triggers the SQL compensation path (a store double that raises).
- `tests/test_document_tools.py` — JSON shapes including `page`, blank-query
  error string, no-hit message, `list_documents` namespaces, and that tool
  schemas expose no service/vector-store parameters.

Update existing tests:

- `tests/test_container.py` — `documents`/`document_chunks`/`rag_meta` exist,
  `document_service` and `vector_store` are wired, the index directory is
  created, tool count is now **38** including `search_documents` and
  `list_documents`.
- `tests/test_config.py` — new defaults and env precedence.
- `tests/test_cli_commands.py` — `/ingest` (including `--force`) and
  `/documents` handlers (success, no argument, missing path) and their presence
  in `COMMANDS`.

FAISS and pypdf run fully offline, so every test uses real FAISS plus
`FakeEmbeddings`; no OpenAI calls and no real `chatbot_memory.db` are touched.

---

## 16. Verification

```bash
uv sync
uv run pytest

# faiss sanity
uv run python -c "import faiss, numpy as np; print('faiss', faiss.__version__); i=faiss.IndexIDMap2(faiss.IndexFlatIP(4)); v=np.eye(4, dtype='float32'); faiss.normalize_L2(v); i.add_with_ids(v, np.array([1,2,3,4])); print(i.search(v[:1], 2))"

# pypdf sanity
uv run python -c "import pypdf; print('pypdf', pypdf.__version__)"

# schema + index dir sanity (idempotent)
uv run python -c "from agentic_chatbot.database import create_connection, init_schema; c=create_connection('tmp_rag.db'); init_schema(c); init_schema(c); print(sorted(r[0] for r in c.execute(\"select name from sqlite_master where type='table'\")))"
```

Manual CLI pass:

```text
mkdir docs
# add 2-3 .md files and one text-based PDF, e.g. docs/handbook.md, docs/policy.pdf
uv run agentic-chatbot
/ingest docs handbook
/documents
What does the handbook say about onboarding?      → ● Executing tool: search_documents
/ingest docs policies
What does the policy PDF say on page 4?           → result cites source + page
/ingest missing-folder                            → warning, no crash
/ingest docs handbook                             → "0 indexed, N skipped" (dedupe)
/ingest docs handbook --force                     → re-embeds and rebuilds the index
```

Add a scanned (image-only) PDF to `docs/` and confirm it appears in the ingest
error list as "no extractable text (scanned PDF? OCR is not supported)" while the
other files still index. Inspect `data/faiss/`: one `*.faiss` file per namespace.

---

## 17. Risks and mitigations

1. **FAISS / pypdf wheel availability.** Verified for this interpreter:
   `faiss-cpu 1.16.0`, `pypdf 7.1.0`. If a future Python upgrade breaks either,
   `VectorIndexStore` can be reimplemented over numpy, and the loader seam
   (`loaders.load_file`) lets the extractor be swapped without touching the
   service.
2. **Scanned/image-only PDFs.** `pypdf` cannot OCR them. They are reported as
   per-file errors; the plan deliberately does not add `pytesseract`/OCR.
   Document the limitation in the README.
3. **PDF extraction quality.** Multi-column layouts, tables, and ligatures can
   extract imperfectly. Chunking per page limits the damage, and answers cite
   page numbers so the user can verify. Re-ingest with `--force` after editing.
4. **Large PDFs.** `rag_max_pdf_bytes` (20 MB) and `rag_max_pdf_pages` (200)
   bound memory and cost; truncation is surfaced as a warning.
5. **Index/DB divergence.** The ordering and compensation delete in Section 9
   keep both sides consistent. If `data/faiss/` is lost, re-run
   `/ingest docs <namespace> --force`; without `force`, unchanged files are
   skipped by hash and their vectors stay missing.
6. **Embedding dimension/model changes.** Guarded in `rag_meta` and on index
   load; raises with remediation instead of silently returning garbage.
7. **Delete-and-recreate namespaces.** `remove()` drops the index file when
   empty, so renaming a namespace leaves no stale vectors.
8. **Tool count growth.** 38 schemas are sent on every call (caveat 10 in
   `ARCHITECTURE.md`); the retriever adds two. Acceptable now; revisit gating if
   latency grows.
9. **Cost/latency at ingest.** Batched (64) embedding calls, per-file size caps,
   hash-based skip unless `force`.
10. **Concurrency.** `threading.Lock` in `VectorIndexStore` plus atomic
    `os.replace` writes; SQLite is already shared with `check_same_thread=False`.
    Under a future multi-worker API, two processes must not write the same index —
    revisit then.

---

## 18. Task order

1. `pyproject.toml` deps + `uv sync`; run the FAISS and pypdf sanity commands.
2. `config.py` settings + `embeddings.py` factory; extend `test_config.py`.
3. `models.py` dataclasses + `database.py` tables + `rag_meta` guard.
4. `loaders.py` (text + PDF) + `tests/test_loaders.py`.
5. `vector_store.py` + `tests/test_vector_store.py` (pure FAISS, no network).
6. `DocumentsRepository` (+ `replace_document`, `chunk_ids`, `chunks_by_ids`) +
   `tests/test_documents_repository.py`.
7. `services/document_service.py` (including `force`, page provenance, PDF
   limits) + `FakeEmbeddings` + `tests/test_document_service.py`.
8. `tools/documents.py`, `registry.py`, `container.py`; update
   `test_container.py`.
9. `/ingest` (`--force`) + `/documents` + `session.document_service`; update
   `test_cli_commands.py`.
10. `.env.example`, `.gitignore`, `docs/.gitkeep`, `ARCHITECTURE.md`, `README.md`.
11. Full `uv run pytest` + manual CLI pass (including one real PDF and one
    scanned PDF).
