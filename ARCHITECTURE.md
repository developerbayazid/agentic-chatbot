# Architecture

This document describes how the chatbot is structured **right now**: a
single-process, interactive CLI application built with LangChain, LangGraph,
SQLite, and FAISS. FastAPI has been intentionally removed for the moment. The
layout below exists so that adding an HTTP layer later is a wiring change rather
than a rewrite.

> For setup and usage instructions, see `README.md`.

---

## 1. High-level goals

1. Keep the CLI working exactly as before (threads, streaming, titles, history).
2. Put all business logic in framework-agnostic services.
3. Keep persistence (SQLite + LangGraph checkpoints) behind a small repository.
4. Make the graph definition independent of how it is invoked.
5. Make a future FastAPI layer a thin adapter over the service layer.
6. Route tool calls through a standard LangGraph loop backed by one registry.
7. Support retrieval over local documents (text + PDF) without adding a second
   database: text lives in SQLite, vectors in one FAISS index per namespace.

The guiding rule: **the CLI and a future API are interchangeable presentations
of the same services.** No business logic lives in `cli/`, and no HTTP or
terminal concepts leak into `services/`.

---

## 2. Project layout

```text
agentic-chatbot/
├── ARCHITECTURE.md              # This document
├── README.md
├── pyproject.toml
├── uv.lock
├── .env / .env.example
├── chatbot_memory.db            # SQLite: thread metadata + LangGraph checkpoints
├── docs/                        # User documents indexed by /ingest
├── data/faiss/                  # One FAISS index file per namespace
├── tests/                       # Pytest suite: fakes, temp SQLite databases
├── notebooks/                   # Learning notebooks
│
└── src/
    └── agentic_chatbot/
        ├── __init__.py          # Lazy export of main() for the console script
        ├── __main__.py          # python -m agentic_chatbot entry point
        ├── container.py         # Composition root: builds all shared resources
        │
        ├── cli/                 # Terminal presentation (Rich + prompt_toolkit)
        │   ├── __init__.py      # exports: main, run_session, dispatch, COMMANDS
        │   ├── theme.py         # design system: emerald palette + surfaces
        │   ├── glyphs.py        # terminal-safe symbol fallback
        │   ├── background.py    # emerald grid + neural-node decoration
        │   ├── console.py       # Rich rendering (hero, messages, commands)
        │   ├── chat.py          # streaming turns + tool timing + status
        │   ├── commands.py      # command table, handlers, dispatch
        │   ├── registry.py      # Command record, lookup, fuzzy matching
        │   ├── session.py       # per-run state shared by handlers
        │   ├── input.py         # framed prompt + prompt_toolkit completion
        │   ├── picker.py        # interactive /threads session picker
        │   └── app.py           # interactive loop + main()
        │
        ├── config.py            # pydantic-settings Settings (env + .env)
        ├── llm.py               # ChatOpenAI factory
        ├── embeddings.py        # OpenAIEmbeddings factory
        ├── loaders.py           # text/Markdown/PDF -> page-aware sections
        ├── vector_store.py      # one FAISS index per namespace
        ├── database.py          # SQLite connection + schema creation
        ├── models.py            # Domain dataclasses (Thread, Note, Document, ...)
        ├── repository.py        # Thread, Notes, Documents repositories
        │
        ├── graph/
        │   ├── __init__.py
        │   ├── state.py         # ChatState (messages + add_messages reducer)
        │   ├── nodes.py         # create_chat_node(llm)
        │   └── workflow.py      # build_chatbot(llm, checkpointer, tools)
        │
        ├── services/
        │   ├── __init__.py
        │   ├── thread_service.py  # Thread lifecycle (CRUD + checkpoint cleanup)
        │   ├── title_service.py   # Automatic title generation
        │   ├── document_service.py # Ingestion, chunking, retrieval
        │   └── chat_service.py    # Streaming turns, history, state access
        │
        └── tools/
            ├── __init__.py
            ├── builtin.py         # calculator, get_current_time
            ├── utilities.py       # local helpers (hash, base64, units, ...)
            ├── life.py            # loan, tip, BMI, age, timezone, fuel
            ├── notes.py           # database-backed note tools
            ├── documents.py       # search_documents / list_documents
            ├── mocks.py           # simulated API tools (weather, search, ...)
            └── registry.py        # STATIC_TOOLS / get_tools(repo, documents)
```

---

## 3. Layered architecture

```text
┌──────────────────────────────────────────────────────────────┐
│ Presentation layer                                           │
│   cli/                                                       │
│   - theme.py       emerald design system: palette + surfaces │
│   - background.py  emerald grid + neural-node decoration     │
│   - glyphs.py      terminal-safe symbol fallback             │
│   - input.py       framed prompt + completion, history, keys │
│   - commands.py    one command table: handlers + dispatch    │
│   - console.py     Rich rendering: hero, messages, commands  │
│   - chat.py        streaming TurnEvents -> Rich output       │
│   - session.py     per-run state (thread id, console, ask)   │
│   - app.py         the loop + main()                         │
│   (future: FastAPI routers do the same job)                  │
└───────────────────────────┬──────────────────────────────────┘
                            │ calls
┌───────────────────────────▼──────────────────────────────────┐
│ Service layer (framework-agnostic)                           │
│   ChatService     ThreadService     TitleService             │
│   DocumentService                                            │
│   - orchestration   - lifecycle      - prompt + fallback     │
│   - streaming       - validation     - model call            │
│   - history         - ingestion      - titles                │
│                     - retrieval (search + citations)         │
└───────────────┬───────────────────────────────┬──────────────┘
                │                               │
┌───────────────▼──────────────┐  ┌─────────────▼──────────────┐
│ Persistence & retrieval      │  │ Graph orchestration        │
│   ThreadRepository           │  │   StateGraph(ChatState)    │
│   NotesRepository            │  │   START → chat_node        │
│   DocumentsRepository        │  │        ⇄ tools → END       │
│   database.py                │  │   compiled w/ checkpointer │
│   SqliteSaver (checkpoints)  │  │   llm.py (ChatOpenAI)      │
│   loaders.py / vector_store  │  │   tools/registry.py        │
└──────────────────────────────┘  └────────────────────────────┘

        container.py constructs and connects every box above.
```

### Dependency direction

- `cli` → `container` → (`config`, `database`, `repository`, `graph`, `llm`,
  `embeddings`, `loaders`, `vector_store`, `services`, `tools`)
- `services.chat` → compiled graph + `ThreadService` + `TitleService`
- `services.thread` → `ThreadRepository` + `SqliteSaver`
- `services.document` → `DocumentsRepository` + `VectorIndexStore` +
  `Embeddings` + `loaders`
- `graph.workflow` → `graph.nodes` → `graph.state` (+ LangGraph `ToolNode`)
- `tools.registry` → `tools.builtin`, `tools.notes`, `tools.documents`
- `vector_store` → `faiss` + `numpy`; `loaders` → `pypdf`
- `repository` → `models` + `sqlite3`

Nothing imports the CLI, `graph/` never imports `services/`, and
`services/document_service.py` knows nothing about the graph, CLI, or HTTP. That
one-way flow is what keeps the business logic reusable.

Within `cli/`, the imports also point one way:
`app → {commands, chat, input, session}`, `commands → {registry, console, session}`,
`chat → {console}`, `input → {theme, glyphs, registry, session}`,
`console → {theme, background, glyphs, models}`, `background → {theme, glyphs}`.
`registry` has no dependencies beyond the standard library (and `theme` only on
Rich), which is why command lookup, fuzzy matching, and the palette can be
unit-tested in isolation.

---

## 4. Composition root: `container.py`

`ChatbotContainer` is the only place where shared resources are created. The
construction order matters:

```python
class ChatbotContainer:
    def __init__(self, settings: Settings):
        self.connection = create_connection(settings.database_path)  # 1
        init_schema(self.connection)                                 # 2

        self.checkpointer = SqliteSaver(self.connection)             # 3
        self.checkpointer.setup()                                    # 4

        self.llm = create_llm(settings)                              # 5
        self.notes_repository = NotesRepository(self.connection)    # 5a
        self.embeddings = create_embeddings(settings)               # 5b
        self.documents_repository = DocumentsRepository(            # 5c
            self.connection
        )
        self.vector_store = VectorIndexStore(                       # 5d
            Path(settings.rag_index_path), settings.embedding_dimensions
        )
        self.document_service = DocumentService(                    # 5e
            self.documents_repository, self.vector_store, self.embeddings,
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
            top_k=settings.rag_top_k,
            min_score=settings.rag_min_score,
        )
        self.tools = get_tools(                                     # 5f
            self.notes_repository, self.document_service
        )
        self.chat_llm = create_llm(settings, self.tools)             # 5g
        self.chatbot = build_chatbot(                               # 6
            self.chat_llm, self.checkpointer, self.tools
        )

        self.thread_repository = ThreadRepository(self.connection)   # 7
        self.thread_service = ThreadService(
            self.thread_repository, self.checkpointer
        )
        self.title_service = TitleService(self.llm)
        self.chat_service = ChatService(
            self.chatbot,
            self.thread_service,
            self.title_service,
            settings.system_prompt + TOOL_GUIDANCE,
        )

    def close(self) -> None:
        self.connection.close()
```

1. Open one SQLite connection (`check_same_thread=False`) with
   `row_factory = sqlite3.Row`.
2. Create the `threads`, `notes`, `documents`, `document_chunks`, and
   `rag_meta` tables if missing.
3. Wrap the same connection in LangGraph's `SqliteSaver`.
4. Let the checkpointer create/upgrade its own tables.
5. Build the untooled chat model from settings (used for title generation).
   5a. Build the notes repository over the shared connection.
   5b. Build the OpenAI embeddings model (no network call at construction).
   5c. Build the documents repository over the shared connection.
   5d. Open the per-namespace FAISS index directory.
   5e. Build the document service (ingest, chunk, embed, search).
   5f. Load the tool registry, binding note and document tools.
   5g. Build a tool-bound copy of the model (`bind_tools`).
6. Compile the graph exactly once, passing the bound model and the tools.
7. Wire the repository and services. The chat service receives the system
   prompt plus `TOOL_GUIDANCE`, a short tool-selection policy (when to use
   documents, notes, and calculators, and how to report empty or failed tool
   results).

`build_container(settings=None)` is the public factory. The CLI uses it today; a
FastAPI lifespan will use the same function later. Creating the graph once and
reusing it is important: LangGraph state is persisted per `thread_id` in the
checkpointer, not held in the compiled object.

---

## 5. Module reference

### `config.py`

Pydantic-settings reads environment variables and `.env` (relative to the
current working directory).

| Setting           | Env var           | Default                           |
| ----------------- | ----------------- | --------------------------------- |
| `openai_api_key`  | `OPENAI_API_KEY`  | `None` (falls back to SDK)        |
| `database_path`   | `DATABASE_PATH`   | `chatbot_memory.db`               |
| `llm_model`       | `LLM_MODEL`       | `gpt-4o-mini`                     |
| `llm_temperature` | `LLM_TEMPERATURE` | `0.0`                             |
| `system_prompt`   | `SYSTEM_PROMPT`   | `You are a helpful AI assistant.` |

RAG settings:

| Setting                | Env var                | Default                   |
| ---------------------- | ---------------------- | ------------------------- |
| `embeddings_model`     | `EMBEDDINGS_MODEL`     | `text-embedding-3-small`  |
| `embedding_dimensions` | `EMBEDDING_DIMENSIONS` | `1536`                    |
| `rag_chunk_size`       | `RAG_CHUNK_SIZE`       | `800`                     |
| `rag_chunk_overlap`    | `RAG_CHUNK_OVERLAP`    | `120`                     |
| `rag_top_k`            | `RAG_TOP_K`            | `4`                       |
| `rag_min_score`        | `RAG_MIN_SCORE`        | `0.15`                    |
| `docs_path`            | `DOCS_PATH`            | `docs`                    |
| `rag_index_path`       | `RAG_INDEX_PATH`       | `data/faiss`              |
| `rag_max_text_bytes`   | `RAG_MAX_TEXT_BYTES`   | `2000000`                 |
| `rag_max_pdf_bytes`    | `RAG_MAX_PDF_BYTES`    | `20000000`                |
| `rag_max_pdf_pages`    | `RAG_MAX_PDF_PAGES`    | `200`                     |

`get_settings()` returns a new `Settings`. Explicit constructor arguments
override both the environment and `.env`, which is what tests do.

### `llm.py`

`create_llm(settings, tools=None)` returns a `ChatOpenAI` configured with the
model, temperature, and API key. Passing `api_key=None` lets the OpenAI SDK
resolve `OPENAI_API_KEY` from the process environment. When `tools` is provided,
the model is wrapped with `bind_tools` so it can emit tool calls; without tools
the raw `ChatOpenAI` is returned (used for title generation).

### `embeddings.py`

`create_embeddings(settings, dimensions=None)` returns an `OpenAIEmbeddings`
configured with `embeddings_model` and `embedding_dimensions`. Construction makes
no network call, so the container can build it at startup.

### `loaders.py`

`load_file(path, max_pdf_pages=200)` turns one file into a `LoadResult`:

- `Section(page, text)` — one per PDF page (`page` is 1-based), or one for a
  text file with `page=None`.
- `truncated` — `True` when a PDF exceeded `max_pdf_pages`.
- `DocumentLoadError` — unsupported suffix, unreadable file, encrypted PDF,
  corrupt PDF, or no extractable text (scanned/image-only PDF; no OCR).

Supported suffixes: `.md`, `.markdown`, `.txt`, `.rst`, `.pdf`. Text is
normalized (NULs removed, CRLF to LF, blank runs collapsed, stripped).

### `vector_store.py`

`VectorIndexStore(directory, dimensions)` keeps **one FAISS index per
namespace**:

- `faiss.IndexIDMap2(faiss.IndexFlatIP(dim))` with `document_chunks.row_id` as
  the int64 vector id; vectors are L2-normalized, so scores are cosine
  similarity.
- Indexes load lazily from `{directory}/{slug}-{sha1}.faiss` and are written
  atomically (`write_index` to a temp file, then `os.replace`).
- `add`, `replace` (remove + add + one save), `remove`, `search(namespaces,
  vector, k)`, `stats`.
- A removed-to-empty namespace deletes its index file. Loading an index whose
  dimension differs from the configured one raises with remediation.
- Cross-namespace search is a merge of the per-index results.

### `database.py`

- `create_connection(path)` — opens SQLite with `check_same_thread=False` and
  `sqlite3.Row` rows.
- `init_schema(connection, embedding_dimensions=1536)` — creates the `threads`,
  `notes`, `documents`, `document_chunks`, and `rag_meta` tables, and records or
  validates the embedding dimension.
- `THREADS_TABLE_SCHEMA`, `NOTES_TABLE_SCHEMA` — the DDL in one place each.

### `models.py`

- `Thread` — frozen dataclass: `thread_id`, `title`, `created_at`,
  `updated_at`. Used by the repository, services, and CLI (and later Pydantic
  response schemas).
- `Note` — frozen dataclass: `note_id`, `thread_id`, `title`, `content`,
  `created_at`. Used by `NotesRepository` and the note tools.
- `Chunk` — frozen dataclass: `content`, `page` (optional PDF page). The
  repository/service boundary for one text chunk.
- `Document` — frozen dataclass: `doc_id`, `namespace`, `source`, `title`,
  `content_hash`, `size_bytes`, timestamps.
- `DocumentHit` — frozen dataclass returned by retrieval: chunk/document
  identity, `namespace`, `title`, `source`, `chunk_index`, `page`, `content`,
  and `score` (cosine similarity, higher is better).
- `TurnEvent` — frozen dataclass emitted by `ChatService.stream_turn`:
  - `type="token"`, `content="..."` for each streamed chunk
  - `type="tool_call"`, `name=...`, `content=<JSON args>` when the model requests
    a tool
  - `type="tool_result"`, `name=...`, `content="..."` when a tool returns
  - `type="done"`, `title=...` (or `None`) once the turn is persisted

`TurnEvent` deliberately contains no terminal/HTTP concepts, so it can be mapped
to plain text or Server-Sent Events without change.

### `repository.py`

`ThreadRepository` owns **all SQL against the `threads` table**:

| Method                       | SQL                       |
| ---------------------------- | ------------------------- |
| `create(title="New chat")`   | `INSERT`, returns `Thread` |
| `get(thread_id)`             | `SELECT ... WHERE`        |
| `list_all()`                 | `SELECT ... ORDER BY updated_at DESC, created_at DESC` |
| `exists(thread_id)`          | `SELECT 1`                |
| `update_title(id, title)`    | `UPDATE title, updated_at` |
| `touch(id)`                  | `UPDATE updated_at`       |
| `delete(id)`                 | `DELETE`                  |

It holds one cursor over the shared connection and commits after each write.
No business rules live here (no title truncation, no checkpoint cleanup).

`NotesRepository` owns **all SQL against the `notes` table**:

| Method                              | SQL                                                            |
| ----------------------------------- | -------------------------------------------------------------- |
| `create(thread_id, title, content)` | `INSERT`, returns `Note`                                       |
| `get(thread_id, note_id)`           | `SELECT ... WHERE thread_id AND note_id`                       |
| `list_all(thread_id)`               | `SELECT ... WHERE thread_id ORDER BY created_at ASC`           |
| `search(thread_id, query)`          | `SELECT ... WHERE thread_id AND (title/content LIKE ?)`        |
| `delete(thread_id, note_id)`        | `DELETE ... WHERE thread_id AND note_id`                       |

Every method takes a `thread_id`, and all SQL filters on it. Append, list,
search, and delete therefore cannot cross conversation boundaries. Notes are
durable: they live in `notes` table rows, independent of LangGraph checkpoints,
so they survive process restarts.

`DocumentsRepository` owns **all SQL against `documents` and
`document_chunks`** (never vectors):

| Method | Behaviour |
| --- | --- |
| `get(doc_id)` | one `Document` |
| `find_by_source(namespace, source)` | dedupe lookup |
| `list_documents(namespace=None)` / `list_namespaces()` | listing |
| `replace_document(..., chunks)` | one transaction: upsert `documents`, delete old chunks, insert new chunks (with `page`); returns the document and the new chunk `row_id`s |
| `chunk_ids(doc_id)` | vector ids for a document (read before a replace) |
| `chunks_by_ids(ids)` | joined chunk + document rows keyed by `row_id` |
| `delete_document(doc_id)` | delete chunks, then the document |
| `stats()` | document/chunk/namespace counts |

### `services/thread_service.py`

Coordinates thread lifecycle and enforces small rules:

- `create_thread(title="New chat")` → `Thread`
- `list_threads()`, `get_thread()`, `thread_exists()`
- `rename_thread(id, title)` → truncates to 100 chars via the repository
- `touch_thread(id)` → updates last activity
- `delete_thread(id)` → returns `False` if missing; otherwise deletes LangGraph
  checkpoints **then** metadata

Checkpoint deletion belongs here because "deleting a conversation" means
removing both message state and its metadata.

### `services/title_service.py`

`generate_title(user_message)` asks the LLM for a 3–6 word title and truncates to
100 chars. The prompt is a module constant. On any failure (or empty output) it
falls back to the first 50 characters of the user message, then `"New chat"`.
Exceptions never escape.

### `services/document_service.py`

Ingestion and retrieval, independent of the CLI:

- `ingest_path(path, namespace=None, force=False)` → `IngestResult`
  (`files_seen`, `files_indexed`, `files_skipped`, `chunks_created`,
  `namespaces`, `errors`, `warnings`). A file or directory; missing paths and
  unreadable files are reported, never raised.
- `ingest_file(path, namespace, force=False)` → `(chunks, skipped, warning)`.
  Loads sections, hashes the text, skips unchanged `(namespace, source)` unless
  `force`, chunks each section independently (preserving `page`), embeds in
  batches of 64, then writes SQL and the index.
- **Consistency order:** embed → `replace_document` (SQL transaction) →
  `vector_store.replace`. If the index write fails, the SQL rows are deleted so
  no orphan chunk can outlive a failed index update.
- `search(query, namespace=None, k=None)` → `DocumentHit`s ordered by score;
  blank query returns `[]`, `k` is clamped to 1–10, and hits below
  `rag_min_score` are filtered so "nothing relevant" is representable.
- `list_documents`, `list_namespaces`, `delete_document`, `stats`.

### `services/chat_service.py`

The heart of the conversation logic.

- `get_config(thread_id)` → `{"configurable": {"thread_id": ...}}`, the LangGraph
  thread key.
- `get_messages(thread_id)` → reads `chatbot.get_state(config).values["messages"]`
  from the checkpointer. Used for history.
- `stream_turn(thread_id, user_message)` → generator of `TurnEvent`:
  1. Read existing messages; detect whether this is the **first** turn.
  2. Build input messages: `[SystemMessage]` on the first turn, then
     `HumanMessage(user_message)`.
  3. Call `chatbot.stream(..., stream_mode=["messages", "updates"], version="v2")`.
  4. For each `"messages"` chunk from `chat_node` whose content is a non-empty
     string, yield a `token` event. Chunks from other nodes (notably the `tools`
     node's `ToolMessage` results) are skipped so raw tool output never leaks
     into the answer stream.
  4b. For `"updates"` chunks: an `AIMessage` with `tool_calls` from `chat_node`
     yields `tool_call` events (arguments as JSON); a `ToolMessage` from `tools`
     yields `tool_result` events.
  5. After streaming, on the first turn generate and save the title, then yield
     `done` with that title; otherwise touch the thread and yield `done` with
     `title=None`.

`ChatService` does **not** print, catch errors, or know about SSE. Callers decide
how to expose events.

### `graph/`

- `state.py` — `ChatState(TypedDict)` with
  `messages: Annotated[list[BaseMessage], add_messages]`. The `add_messages`
  reducer appends new messages instead of replacing the list.
- `nodes.py` — `create_chat_node(llm)` returns a node that invokes the model on
  `state["messages"]` and returns `{"messages": [response]}`. Injecting the LLM
  keeps the node testable.
- `workflow.py` — `build_chatbot(llm, checkpointer, tools=None)` wires
  `START → chat_node`, then:
  - with tools: a `ToolNode` from `langgraph.prebuilt` plus conditional routing
    (`tools_condition`) — `chat_node → tools → chat_node` when the model emits
    tool calls, otherwise `chat_node → END`;
  - without tools: `chat_node → END` exactly as before.

  The result is the compiled graph used by `ChatService`. The default recursion
  limit bounds tool loops.

Adding a node later (router, memory) means adding it in `nodes.py` and the edge
in `workflow.py`; no service or CLI code changes.

### `tools/`

All tools are `@tool`-decorated functions. Tools that need an external service
return clear `"Error: ..."` strings instead of raising, so the model can recover.

Tool selection is intent-driven, not forced: `container.py` appends
`TOOL_GUIDANCE` to the system prompt and each description states when it should
be used. General-knowledge questions are answered directly; references to the
user's documents, uploads, or notes require the matching tool, and the model is
told never to claim a search it did not perform.

- `builtin.py` — core tools:
  - `calculator(expression)` — safe arithmetic (AST whitelist, no `eval`).
  - `get_current_time(timezone=None)` — ISO 8601 timestamp, optional IANA zone.
- `utilities.py` — local, key-free helpers: `generate_uuid`,
  `generate_password`, `hash_text`, `base64_encode`, `base64_decode`,
  `format_json`, `regex_search`, `summarize_text` (extractive), `convert_units`.
- `life.py` — fully local everyday calculators: `calculate_loan_payment`,
  `calculate_tip_split`, `calculate_bmi`, `calculate_age`, `days_between`,
  `convert_timezone` (via `zoneinfo`), `estimate_fuel_cost`.
- `notes.py` — database-backed, per-conversation note taking via
  `create_note_tools(repository)`: `save_note`, `list_notes`, `search_notes`,
  `delete_note`. Each tool declares a `config: RunnableConfig` parameter (injected
  by LangChain, hidden from the model schema) and reads
  `config["configurable"]["thread_id"]` to scope every repository call. Notes
  therefore persist across turns and restarts while staying private to the thread
  that created them.
- `documents.py` — retrieval tools via `create_document_tools(service)`:
  - `search_documents(query, namespace="", k=4)` — cosine search over the
    ingested knowledge base; returns JSON hits with `title`, `source`,
    `namespace`, `chunk_index`, `page`, `score`, and `content`. Blank queries and
    no-hit results are plain strings, never exceptions. An unknown namespace
    returns `"error": "Unknown namespace."` plus the valid `namespaces` list
    instead of a silent empty result, and an empty namespace searches all of
    them.
  - `list_documents(namespace="")` — known namespaces plus document metadata.
    Namespaces are chosen at ingest time, so the model can discover them here.
- `mocks.py` — simulated implementations of common API-backed tools:
  `web_search`, `fetch_url`, `get_news`, `get_weather`, `get_stock_price`,
  `convert_currency`, `send_email`, `send_slack_message`,
  `create_calendar_event`, `list_calendar_events`, `translate_text`,
  `find_recipe`, `get_holidays`, `track_package`. Each response carries
  `"mock": true`; calendar events live in memory for the process lifetime.
  Replace a tool body with a real client call when its credentials are
  available — signatures and return shapes can stay the same.
- `registry.py` — `STATIC_TOOLS` (32 repository-free tools) plus
  `get_tools(notes_repository, document_service=None)`, which appends the four
  note tools and, when a document service is supplied, the two retrieval tools
  for a total of 38. `container.py` passes the result to both `create_llm` and
  `build_chatbot`.

**Adding a tool** is additive:

```python
from langchain_core.tools import tool

@tool
def word_count(text: str) -> str:
    """Count the words in a text."""  # shown to the model
    return str(len(text.split()))
```

Append the function to `STATIC_TOOLS` in `registry.py`. Nothing else changes:
`create_llm` binds the new schema and `ToolNode` can execute it. Prefer
returning a plain string or JSON string; return `"Error: ..."` for bad input so
the model can correct itself instead of the run failing.

Tools that need shared state (notes, documents) are built by a
`create_*_tools()` factory that closes over its dependency, and
`get_tools(notes_repository, document_service)` includes them. This keeps tools
dependent only on their repository/service rather than on global state.

Mock tools are intentionally honest: JSON responses include `"mock": true`, no
network calls are made, and the modeled state (calendar) lives in module memory
for the process lifetime. Notes are the exception: they are durable SQLite rows.

### `cli/`

Presentation only. The package turns `TurnEvent`s and service calls into a
polished terminal experience, and nothing else.

| Module        | Responsibility |
| ------------- | -------------- |
| `registry.py` | `Command` and `Completion` dataclasses, `normalize`, `resolve`, `grouped`, `suggest` (prefix, then fuzzy), `similar_commands` (difflib), `split_input`. No I/O, no rendering, no service imports — pure and directly unit-tested. |
| `commands.py` | `COMMANDS: list[Command]` — the single source of truth — plus every handler and `dispatch(session, text) -> bool`. `dispatch` returns `False` for non-slash input so the caller forwards it to the LLM, and `True` when it handled the input (including reporting an unknown command, which is never forwarded). |
| `theme.py` | The design system: the emerald palette (brand, type ramp, status colours), background/surface colours, the resolved `Palette` with named style roles, and the shared `RICH_THEME`. Every colour lives here; no component hardcodes one. |
| `background.py` | The emerald grid + neural-node decoration: `grid_lines` (a sparse lattice with occasional emerald nodes), `stamp_center`/`banner` (overlay a clean, centred lockup over the grid), and `grid_unicode_ok` for the Unicode→ASCII fallback. Static text — no animation, no per-token redraw cost. |
| `console.py` | Rich rendering in the emerald-grid design: the framed welcome hero (`show_welcome` — grid backdrop, brand lockup, live status bullets, quick-start shortcuts), `show_status_banner`, `show_help`, `show_command_help`, `show_threads`, `show_history`, `user_message` (`YOU`), `assistant_header` (`BAYAZID AI`), `stream_token`, `markdown_block`, `tool_call` (`● Executing tool: …`), `tool_result` (`✓ Completed · 0.3s` / `✗ Failed`), `error`, `notice`/`success`/`warning`, and the `StatusSnapshot` record. All layout lives here; colours come from `theme.py`. |
| `chat.py` | `process_message` maps `TurnEvent`s to renderer calls and measures real tool elapsed time; `build_status` collects display-safe runtime facts. The `_Response` buffer decides between live streaming and Markdown rendering and closes a streamed line before tool activity. |
| `session.py` | `ChatSession` — mutable per-run state: container, console, `current_thread_id`, `running`, and an injectable `ask` used by handlers that need an argument. Exposes `thread_service`/`chat_service`/`settings` convenience properties and `process()`. |
| `input.py` | `CommandCompleter` (command names, then per-command argument completions), `framed_message` (the width-adaptive top-rule + left-rail composer), `build_prompt_session` (framed message + `bottom_toolbar` status bar), `read_input`, `make_ask`, and `PlainPrompt` for terminals where prompt_toolkit cannot attach. |
| `picker.py` | Interactive `/threads` session picker: a prompt_toolkit `Application` with a search buffer and a live table (recency, message count, active marker). `relative_time`, `build_rows`, `filter_rows` are pure; `pick` runs the application and returns the chosen thread, falling back to the static list off a TTY. |
| `glyphs.py` | `g(name)` returns a Unicode or ASCII symbol depending on the stdout encoding, preventing `UnicodeEncodeError` on legacy code pages. |
| `app.py` | `run_session(container, console, prompt_session=None)` and `main()`. Owns the loop, resumes the most recent thread, and always closes the connection in a `finally` block. |

**Command definition.** A command carries its name, description, category,
usage, example, behaviour, argument description, handler, and optional
`arg_completer`:

```python
@dataclass(frozen=True)
class Command:
    name: str
    description: str
    category: str
    usage: str
    example: str
    behavior: str
    arguments: str
    handler: Callable[[ChatSession, str], None]
    arg_completer: Callable[[ChatSession, str], list[Completion]] | None = None
```

Two categories exist — `General` (`/help`, `/clear`, `/status`, `/version`,
`/exit`) and `Conversation` (`/new`, `/threads`, `/history`, `/rename`,
`/delete`) — and `CATEGORY_ORDER` fixes their display order.

**Dispatch.** Slash input never reaches the model. `dispatch` looks the name up
with `resolve` (accepting `help` and `/help` alike); an unknown name triggers
`similar_commands` and an inline "Did you mean?" warning. Only
non-slash text returns `False` and becomes a chat turn.

**Argument completion.** `/delete` declares `arg_completer=_thread_ids`,
which reads `ThreadService.list_threads()` at completion time and returns
`Completion(thread_id, title)` pairs. Thread IDs therefore always come from the
database and cannot drift from the real state.

**Streaming and Markdown.** `_Response` buffers the first
`min(newline, 80 chars)` of each response. If that prefix starts a Markdown block
(fence, heading, quote, table, bullet, numbered list, rule) the rest is buffered
and rendered with `rich.markdown.Markdown`; otherwise the buffer is flushed and
tokens stream live. Tool events flush the buffer first so ordering reads
naturally, and an error flushes rather than discards partial output.

**Terminal safety.** `build_prompt_session` returns `None` when prompt_toolkit
cannot obtain a console (piped input, CI, some legacy shells); `app.py` then
substitutes `PlainPrompt`, which reads `input()`. The command set, dispatch, and
rendering are identical on both paths.

**Error handling.** `process_message` catches stream/LLM failures, logs the
traceback at DEBUG, and shows a concise inline error. `run_session` catches
`KeyboardInterrupt` per turn and any other exception per iteration, so a
recoverable error never ends the session. `main()` always closes the connection.

---

## 6. Request/flow diagrams

### Sending a message

```text
User types text
      │
      ▼
app.run_session → commands.dispatch(session, text)
      │
      ├─ starts with "/" ? ── yes ─► resolve in COMMANDS
      │                              ├─ found  → handler(session, argument)
      │                              └─ missing → "Did you mean?" warning  (stop)
      │
      └─ no
      ▼
ChatSession.process(text)          (never reached for slash input)
      │
      ▼
cli.chat.process_message(console, chat_service, thread_id, text)
      │
      ├─ console.user_message(...) / assistant_header(...)
      ▼
ChatService.stream_turn(thread_id, text)
      │
      ├─ chatbot.get_state(config) ──► checkpointer (SQLite)
      │        existing messages? ──► first turn?
      │
      ├─ build [SystemMessage?] + HumanMessage
      │
      ├─ chatbot.stream(...)  ──► LangGraph ──► ChatOpenAI
      │        chat_node tokens ──► yield TurnEvent(token, content)
      │        chat_node updates ─► yield TurnEvent(tool_call, name, args)
      │        tools updates ─────► yield TurnEvent(tool_result, name, result)
      │        (tools node loops back to chat_node)
      │
      ├─ if first turn: TitleService.generate_title(text)
      │        └─ ThreadService.rename_thread(thread_id, title)
      │  else:          ThreadService.touch_thread(thread_id)
      │
      └─ yield TurnEvent(done, title=title|None)
      │
      ▼
cli.chat._Response routes each token:
      ├─ buffered prefix starts a Markdown block → render with Rich Markdown
      └─ otherwise                              → stream token, live
tool_call / tool_result events flush the buffer, then render a status line
done → close the message; print the new title if this was the first turn
```

### Tool-calling loop

```text
chat_node (tool-bound LLM)
      │
      ├─ no tool_calls ──────────────────────────────► END
      │
      └─ tool_calls present
             │ tools_condition → "tools"
             ▼
        ToolNode executes each call
             ├─ calculator, get_current_time        (local)
             ├─ utilities / life                    (local)
             ├─ notes                               (SQLite, per thread)
             ├─ search_documents / list_documents   (FAISS per namespace)
             └─ mocks                               (simulated data)
             │
             ▼
        ToolMessage(s) appended to state
             │
             └────────────► chat_node (again)

Stream:  messages mode  → chat_node answer tokens
         updates  mode  → AIMessage.tool_calls → tool_call events
                        → ToolMessage           → tool_result events
```

LangGraph's default `recursion_limit` (25) caps the number of round trips.

### Ingesting documents (RAG)

```text
/ingest <path> <namespace> [--force]
      │
      ▼
cli.commands._ingest → DocumentService.ingest_path()
      │
      ├─ walk path (rglob), skip hidden/unsupported/oversized files
      │
      ▼ per file
loaders.load_file()                 (text -> one Section, PDF -> one per page)
      │
      ├─ sha256(section text) == stored hash and not --force ? → skipped
      ▼
RecursiveCharacterTextSplitter      (each section chunked independently,
      │                              Chunk.page preserved for PDFs)
      ▼
OpenAIEmbeddings.embed_documents    (batches of 64)
      │
      ├─ DocumentsRepository.replace_document()   (SQL transaction:
      │      upsert documents, replace document_chunks; returns row_ids)
      ▼
VectorIndexStore.replace()          (one FAISS index per namespace:
      │                              remove old ids, add new ids, atomic save)
      └─ failure → delete the SQL document (compensation) and report the file

/search_documents(query, namespace, k)
      ▼
OpenAIEmbeddings.embed_query → VectorIndexStore.search(namespaces, vector, k)
      ▼
DocumentsRepository.chunks_by_ids → filter score >= rag_min_score → DocumentHits
```

### Creating / switching / deleting threads

```text
/new      → ThreadService.create_thread() → INSERT into threads
            → session.current_thread_id updated
/threads  → ThreadService.list_threads()   → SELECT ordered by updated_at
            → interactive picker (search, ↑/↓, Enter) or static list off-TTY
/history  → ChatService.get_messages()     → checkpointer state
/rename   → ThreadService.rename_thread()  → UPDATE title, updated_at
/delete   → pick a thread (picker or arg), confirm via ask()
            → ThreadService.delete_thread()
              ├─ checkpointer.delete_thread(id)
              └─ repository.delete(id)
            if it was active → create a replacement thread
```

---

## 7. Persistence model

One SQLite database (`DATABASE_PATH`) holds four independent concerns:

### 7.1 Thread metadata — owned by this project

```sql
CREATE TABLE IF NOT EXISTS threads (
    thread_id  TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT 'New chat',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 7.2 Notes — owned by this project

```sql
CREATE TABLE IF NOT EXISTS notes (
    note_id    TEXT PRIMARY KEY,
    thread_id  TEXT NOT NULL,
    title      TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notes_thread_id ON notes (thread_id);
```

`NotesRepository` owns all SQL against this table, and every query filters by
`thread_id`. Notes are independent of LangGraph state: they survive restarts and
are removed only by `delete_note` from their own thread.

`init_schema` also migrates databases created before note scoping: when the
`notes` table lacks `thread_id`, `ALTER TABLE` adds it with a `''` default. Those
legacy rows are intentionally invisible to every conversation.

### 7.3 Knowledge base — owned by this project, vectors in FAISS

```sql
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
);

CREATE TABLE IF NOT EXISTS document_chunks (
    row_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id    TEXT NOT NULL UNIQUE,
    doc_id      TEXT NOT NULL,
    namespace   TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page        INTEGER,
    content     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rag_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

SQLite is authoritative for document text and metadata; it stores **no
vectors**. `document_chunks.row_id` is the id stored in FAISS, so one index
entry maps to exactly one SQL row, and `page` is `NULL` for text files.

Vectors live in `RAG_INDEX_PATH` (`data/faiss/` by default), one
`{slug}-{sha1}.faiss` file per namespace. `rag_meta` records the embedding
dimension and index format version; changing `EMBEDDING_DIMENSIONS` (or the
model) after ingestion raises with remediation instead of mixing vector sizes.
Deleting documents removes the matching ids from their namespace index, and an
index that becomes empty deletes its file. Re-ingesting unchanged files is
skipped by content hash; `/ingest ... --force` re-embeds to rebuild an index.

### 7.4 Conversation state — owned by LangGraph

`SqliteSaver.setup()` creates and manages its own checkpoint tables
(`checkpoints`, checkpoint blobs/writes and migrations; exact names are
LangGraph-version dependent). These store the full message history per
`thread_id` and are **never** modified directly by application code — only
through the compiled graph and `checkpointer.delete_thread()`.

The split is deliberate:

- Metadata is cheap to query and render in a thread list.
- Notes are small durable records, independent of any conversation.
- Document text and metadata are queryable; vectors live in a purpose-built
  index that does not bloat SQLite.
- Message history is managed by the checkpointer so LangGraph can replay and
  resume graph state.

Because all four share one connection, `delete_thread` removes checkpoints and
metadata together while leaving notes and documents intact.

---

## 8. Lifecycle

```text
Settings (env/.env)
      │
build_container()
      ├─ SQLite connection ── init_schema ── threads table
      ├─ SqliteSaver ── setup ── checkpoint tables
      ├─ ChatOpenAI
      ├─ compiled LangGraph (once)
      └─ repository + services
      │
run_session()
      ├─ restore latest thread or create one
      ├─ console.show_welcome() — emerald-grid framed hero + live status
      ├─ build_prompt_session() (or PlainPrompt fallback)
      ├─ input loop → dispatch() for "/", process_message() otherwise
      └─ exit
      │
container.close()   # finally: closes SQLite connection
```

The compiled graph and checkpointer are process-lifetime singletons. A future
FastAPI lifespan will mirror this: build once on startup, close on shutdown.

### Entry points

There is a single startup chain, declared in `pyproject.toml`:

```toml
[project.scripts]
agentic-chatbot = "agentic_chatbot:main"
```

1. `uv run agentic-chatbot` → `src/agentic_chatbot/__init__.py:main()`
2. → `cli/app.py:main()` → `build_container(settings)`
3. → `run_session()` → input loop

Alternatively, `uv run python -m agentic_chatbot` enters through
`__main__.py`, which calls the same `cli.main()`.

---

## 9. Streaming contract

`ChatService.stream_turn` emits a small, transport-neutral contract:

| Event         | Fields                                  | Meaning                                      |
| ------------- | --------------------------------------- | -------------------------------------------- |
| `token`       | `content: str`                          | Incremental assistant text                   |
| `tool_call`   | `name: str`, `content: str` (JSON args) | The model requested a tool                   |
| `tool_result` | `name: str`, `content: str`             | Tool finished; content is its return value   |
| `done`        | `title: str \| None`                    | Turn finished and persisted; title if new    |

The CLI maps these to Rich output through `cli/chat.py`: `token` streams live (or
buffers into a Markdown render), `tool_call`/`tool_result` become status lines,
and `done` closes the message and may print a new title. A future SSE endpoint
maps the same events to:

```text
event: token
data: {"content": "Hello"}

event: tool_call
data: {"name": "calculator", "content": "{\"expression\": \"2+2\"}"}

event: tool_result
data: {"name": "calculator", "content": "4"}

event: done
data: {"title": "Simple Greetings"}
```

Errors are **not** converted into events by the service; the caller decides
(the CLI shows an inline error, an API would emit `event: error` and a 4xx/5xx as
appropriate).

---

## 10. How FastAPI will plug in (migration plan)

The service layer needs no changes. The work is additive:

1. **Lifespan** (`app/main.py` or similar):

   ```python
   @asynccontextmanager
   async def lifespan(app):
       app.state.container = build_container()
       try:
           yield
       finally:
           app.state.container.close()
   ```

2. **Dependency providers** return services from `app.state.container`, e.g.
   `get_chat_service`, `get_thread_service`.

3. **Endpoints** become thin adapters:

   | Endpoint                                  | Service call                              |
   | ----------------------------------------- | ----------------------------------------- |
   | `POST /threads`                           | `thread_service.create_thread()`          |
   | `GET /threads`                            | `thread_service.list_threads()`           |
   | `GET /threads/{id}`                       | `thread_service.get_thread()` → 404 if `None` |
   | `PATCH /threads/{id}`                     | `thread_service.rename_thread()`          |
   | `DELETE /threads/{id}`                    | `thread_service.delete_thread()`          |
   | `GET /threads/{id}/history`               | `chat_service.get_messages()`             |
   | `POST /threads/{id}/messages/stream`      | iterate `chat_service.stream_turn()` → SSE |
   | `POST /threads/{id}/messages`             | iterate `stream_turn()` and join tokens   |

4. **Schemas**: add Pydantic models mirroring `Thread` and `TurnEvent` (or let
   Pydantic validate dataclasses directly).

5. **Validation**: the API layer should check `thread_service.thread_exists()`
   before calling `ChatService`, and translate service results into HTTP errors.
   The services currently assume callers have validated the thread.

### Concurrency consideration

`ChatbotContainer` shares **one** SQLite connection and one `SqliteSaver`
across the process. That is correct for a single-threaded CLI, and
`check_same_thread=False` prevents the obvious error. Under Uvicorn with
concurrent requests (or multiple workers) you should either:

- serialize access with a lock around checkpointer/graph execution, or
- move to per-request connections / a connection pool, or
- run a single worker if traffic is low.

This is a runtime concern, not an architectural one: the container boundary is
where that change belongs.

---

## 11. Extension points

- **New graph node** — add a factory in `graph/nodes.py`, wire the edge in
  `graph/workflow.py`. `ChatService` is unchanged.
- **New tool** — add a `@tool` function and append it to `STATIC_TOOLS` in
  `tools/registry.py` (or build it in a `create_*_tools(repository)` factory for
  stateful tools). `create_llm` binding and `ToolNode` pick it up automatically;
  no graph or service changes.
- **New command** — append a `Command` to `COMMANDS` in `cli/commands.py` with a
  handler and, optionally, an `arg_completer`. Execution, the `/` menu, Tab
  completion, `/help`, and typo suggestions all update automatically.
- **New output style** — add a function in `cli/console.py`; handlers and
  `cli/chat.py` call it, so styling stays in one module.
- **Agents / more routing** — add nodes in `graph/nodes.py` and edges in
  `graph/workflow.py`; `ChatService` is unchanged.
- **Different database** — change `database.py` and `repository.py`; services and
  CLI stay the same.
- **Different model/provider** — change `llm.py` only.
- **Different embeddings/provider** — change `embeddings.py` only; keep
  `EMBEDDING_DIMENSIONS` in sync or re-ingest after the change.
- **New document type** — add the suffix to `loaders.SUPPORTED_SUFFIXES` and a
  branch in `loaders.load_file` that returns `Section`s. Ingestion, chunking,
  indexing, retrieval, and the tools need no changes.
- **Different vector store** — reimplement `VectorIndexStore`'s small API
  (`add`, `replace`, `remove`, `search`, `stats`); `DocumentService` and the
  tools stay the same.
- **Different retrieval policy** — change `DocumentService.search` (top-k,
  minimum score, filtering); the tool surface is already fixed.
- **New presentation** — add a FastAPI (or any other) module that calls the same
  services; never duplicate SQL or graph logic there.
- **More conversation metadata** — extend the `threads` schema and `Thread`
  dataclass, then update `ThreadRepository` and `ThreadService`.

---

## 12. Known caveats

1. **`.env` is cwd-relative** — `Settings` looks for `.env` in the working
   directory. Run the app from the project root, or inject `Settings` explicitly.
2. **Database path default** — `Settings.database_path` defaults to
   `chatbot_memory.db`, while `.env.example` shows `data/chatbot_memory.db`.
   Keep `DATABASE_PATH=chatbot_memory.db` to reuse an existing database.
3. **Single shared connection** — see the concurrency note in section 10.
4. **Title generation is synchronous** — it happens after the last token and
   before the `done` event; a slow title call delays turn completion slightly.
5. **No HTTP layer yet** — FastAPI/Uvicorn remain in `pyproject.toml`
   dependencies but are not imported anywhere in `src/agentic_chatbot/`.
6. **Console script name uses a hyphen** — run `uv run agentic-chatbot`, not
   `agentic_chatbot`. The module entry point is `uv run python -m agentic_chatbot`
   (no `.py`).
7. **Tool loops are bounded by LangGraph's recursion limit** (default 25). A
   model that keeps requesting tools raises `GraphRecursionError`, which the CLI
   reports like any other stream error.
8. **Mock tools return simulated data** — `tools/mocks.py` never calls the
   network and marks responses with `"mock": true`. Do not present their output
   as live data; replace each body with a real client as keys are added.
9. **Mock calendar state is in-memory** — events created by
   `create_calendar_event` reset when the process exits. Notes are the exception:
   they are persisted in SQLite and survive restarts.
10. **Every tool schema is sent to the model on every call** — 38 tools increase
    prompt size and can slow tool selection. Trim `STATIC_TOOLS` (or gate tools
    by config) if latency or cost matters.
11. **prompt_toolkit needs a terminal** — with piped input, CI, or a shell without
    a screen buffer it cannot attach. `build_prompt_session` then returns `None`
    and `PlainPrompt` (plain `input()`) takes over. Commands, dispatch, and
    rendering are identical; only completion and history are unavailable.
12. **Literal symbols follow the console encoding** — `cli/glyphs.py` selects
    Unicode or ASCII at import time from `sys.stdout.encoding`, and
    `cli/background.py` does the same for the grid. On legacy Windows code pages
    (cp1252) you get `*`, `>`, `+`, `x`, `-` instead of `●`, `❯`, `✓`, `✗`, `·`.
    Rich downgrades its own box-drawing characters independently (the hero's
    rounded corners become square, then ASCII).
13. **Markdown rendering buffers the start of a response** — `_Response` holds the
    first newline or 80 characters to classify the message. Plain prose starts
    streaming as soon as that threshold is crossed; Markdown responses appear at
    the end of the message rather than token by token.
14. **PDF extraction is `pypdf` without OCR** — scanned or image-only PDFs have
    no text layer and are reported as per-file ingest errors. Multi-column
    layouts and tables may extract imperfectly; chunks carry page numbers so
    answers can be checked against the source. Re-run `/ingest ... --force` after
    editing a file.
15. **FAISS indexes live outside SQLite** — `data/faiss/` is a second storage
    location. Back it up with the database, or rebuild it with
    `/ingest docs <namespace> --force`. Index files are written atomically and
    guarded by a thread lock, but two processes must not write the same
    namespace index.

---

## 13. Running and verifying

```bash
# Install / sync dependencies
uv sync

# Run the CLI
uv run agentic-chatbot
# or
uv run python -m agentic_chatbot

# Byte-compile the package
uv run python -m compileall -q src/agentic_chatbot

# RAG dependency sanity
uv run python -c "import faiss, pypdf; print(faiss.__version__, pypdf.__version__)"
```

Ingest and query from the CLI (after putting files in `docs/`):

```text
/ingest docs handbook
/documents
What does the handbook say about onboarding?
/ingest docs handbook --force     # rebuild after deleting data/faiss/
```

Run the suite with:

```bash
uv run pytest
```

Tests use `tmp_path` SQLite databases plus fake graph, LLM, title, thread,
checkpointer, and embeddings doubles (`tests/fakes.py`), so no OpenAI calls are
made and the real `chatbot_memory.db` is never opened. FAISS runs against the
fake embeddings, fully offline. Coverage includes configuration precedence,
container wiring and schema creation, thread service CRUD and ordering, checkpoint
cleanup on delete, `ChatService` streaming/title behavior and tool-event emission,
the real `ToolNode` loop, every tool implementation (core, utilities, life, notes,
documents, mocks), notes persistence across separate SQLite connections, thread
isolation of notes, schema migration for legacy note tables, document ingestion
(text and PDF), per-namespace FAISS isolation and persistence, dedupe, retrieval
scoring, CLI rendering, the interactive command loop, and package entry points.

RAG-specific tests:

| File                             | Scope |
| -------------------------------- | ----- |
| `test_loaders.py`                | text normalization, PDF pages/encryption/scanned/truncation, real pypdf parse |
| `test_vector_store.py`           | per-namespace index files, isolation, merge ordering, replace/remove, persistence, dimension guard |
| `test_documents_repository.py`   | document/chunk SQL, page round-trip, delete, namespace listing, idempotent schema |
| `test_document_service.py`       | ingest, dedupe, `force`, page provenance, limits, compensation on index failure |
| `test_document_tools.py`         | `search_documents` / `list_documents` JSON shapes and error strings |

Presentation-specific tests:

| File                             | Scope |
| -------------------------------- | ----- |
| `test_cli_registry.py`           | normalization, lookup, category grouping, prefix and fuzzy suggestions, input splitting |
| `test_cli_commands.py`           | command-table invariants, dispatch routing, every handler, completion providers, secret safety |
| `test_cli_chat.py`               | streaming vs Markdown rendering, tool visibility, error display, interrupt propagation |
| `test_cli_input.py`              | completer behavior, glyph fallback, `run_session` routing and resilience, `ask()` |
| `test_cli_prompt_integration.py` | real `PromptSession` with pipe input: Tab accepts commands and thread IDs, plain text untouched |
| `test_cli_banner.py`             | emerald theme, the framed welcome hero, and the status readout |
| `test_cli_rendering.py`          | background grid, framed input, and timed tool feedback |
| `test_cli_picker.py`             | relative-time/filter/row data and the headless keyboard drive |

The prompt integration tests drive prompt_toolkit through `create_pipe_input()`
with a `DummyOutput`, waiting on buffer state rather than sleeping, so they are
deterministic and need no terminal.

Manual checks in the CLI:

```text
/help
/help delete
/th<tab>            → /threads
/delete <tab>       → real thread IDs with titles
/threds             → "Did you mean? /threads"
/ingest docs handbook
/documents
What does the handbook say about onboarding?
/ingest docs policies --force
What's the weather in Dhaka?
Convert 100 USD to EUR.
Save a note titled "groceries" with milk and eggs.
```

Expect a tool status line before the answer, Markdown structure preserved for
structured responses, mock results marked with `"mock": true`, and RAG answers
citing the document title/source (plus page for PDFs).
