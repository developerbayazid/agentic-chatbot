# Architecture

This document describes how the chatbot is structured **right now**: a
single-process, interactive CLI application built with LangChain, LangGraph, and
SQLite. FastAPI has been intentionally removed for the moment. The layout below
exists so that adding an HTTP layer later is a wiring change rather than a
rewrite.

> For setup and usage instructions, see `README.md`.

---

## 1. High-level goals

1. Keep the CLI working exactly as before (threads, streaming, titles, history).
2. Put all business logic in framework-agnostic services.
3. Keep persistence (SQLite + LangGraph checkpoints) behind a small repository.
4. Make the graph definition independent of how it is invoked.
5. Make a future FastAPI layer a thin adapter over the service layer.
6. Route tool calls through a standard LangGraph loop backed by one registry.

The guiding rule: **the CLI and a future API are interchangeable presentations
of the same services.** No business logic lives in `cli.py`, and no HTTP or
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
├── tests/                       # Pytest suite: fakes, temp SQLite databases
├── notebooks/                   # Learning notebooks
│
└── src/
    └── agentic_chatbot/
        ├── __init__.py          # Lazy export of main() for the console script
        ├── __main__.py          # python -m agentic_chatbot entry point
        ├── cli.py               # Terminal presentation + command loop
        ├── container.py         # Composition root: builds all shared resources
        │
        ├── config.py            # pydantic-settings Settings (env + .env)
        ├── llm.py               # ChatOpenAI factory
        ├── database.py          # SQLite connection + schema creation
        ├── models.py            # Domain dataclasses (Thread, Note, TurnEvent)
        ├── repository.py        # ThreadRepository + NotesRepository
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
        │   └── chat_service.py    # Streaming turns, history, state access
        │
        └── tools/
            ├── __init__.py
            ├── builtin.py         # calculator, get_current_time
            ├── utilities.py       # local helpers (hash, base64, units, ...)
            ├── life.py            # loan, tip, BMI, age, timezone, fuel
            ├── notes.py           # database-backed note tools
            ├── mocks.py           # simulated API tools (weather, search, ...)
            └── registry.py        # STATIC_TOOLS / get_tools(repo)
```

---

## 3. Layered architecture

```text
┌──────────────────────────────────────────────────────────────┐
│ Presentation layer                                           │
│   cli.py                                                     │
│   - reads input(), prints to terminal                        │
│   - parses slash commands                                    │
│   - renders TurnEvent streams                                │
│   (future: FastAPI routers do the same job)                  │
└───────────────────────────┬──────────────────────────────────┘
                            │ calls
┌───────────────────────────▼──────────────────────────────────┐
│ Service layer (framework-agnostic)                           │
│   ChatService     ThreadService     TitleService             │
│   - orchestration   - lifecycle      - prompt + fallback      │
│   - streaming       - validation     - model call             │
│   - history                                                  │
└───────────────┬───────────────────────────────┬──────────────┘
                │                               │
┌───────────────▼──────────────┐  ┌─────────────▼──────────────┐
│ Persistence                  │  │ Graph orchestration        │
│   ThreadRepository           │  │   StateGraph(ChatState)    │
│   database.py                │  │   START → chat_node        │
│   SqliteSaver (checkpoints)  │  │        ⇄ tools → END       │
│   models.py (Thread, Event)  │  │   compiled w/ checkpointer │
│                              │  │   llm.py (ChatOpenAI)      │
│                              │  │   tools/registry.py        │
└──────────────────────────────┘  └────────────────────────────┘

        container.py constructs and connects every box above.
```

### Dependency direction

- `cli` → `container` → (`config`, `database`, `repository`, `graph`, `llm`,
  `services`, `tools`)
- `services.chat` → compiled graph + `ThreadService` + `TitleService`
- `services.thread` → `ThreadRepository` + `SqliteSaver`
- `graph.workflow` → `graph.nodes` → `graph.state` (+ LangGraph `ToolNode`)
- `tools.registry` → `tools.builtin`
- `repository` → `models` + `sqlite3`

Nothing imports the CLI, and `graph/` never imports `services/`. That one-way
flow is what keeps the business logic reusable.

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
        self.tools = get_tools(self.notes_repository)                # 5b
        self.chat_llm = create_llm(settings, self.tools)             # 5c
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
            settings.system_prompt,
        )

    def close(self) -> None:
        self.connection.close()
```

1. Open one SQLite connection (`check_same_thread=False`) with
   `row_factory = sqlite3.Row`.
2. Create the `threads` and `notes` tables if missing.
3. Wrap the same connection in LangGraph's `SqliteSaver`.
4. Let the checkpointer create/upgrade its own tables.
5. Build the untooled chat model from settings (used for title generation).
   5a. Build the notes repository over the shared connection.
   5b. Load the tool registry, binding note tools to that repository.
   5c. Build a tool-bound copy of the model (`bind_tools`).
6. Compile the graph exactly once, passing the bound model and the tools.
7. Wire the repository and services.

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

`get_settings()` returns a new `Settings`. Explicit constructor arguments
override both the environment and `.env`, which is what tests do.

### `llm.py`

`create_llm(settings, tools=None)` returns a `ChatOpenAI` configured with the
model, temperature, and API key. Passing `api_key=None` lets the OpenAI SDK
resolve `OPENAI_API_KEY` from the process environment. When `tools` is provided,
the model is wrapped with `bind_tools` so it can emit tool calls; without tools
the raw `ChatOpenAI` is returned (used for title generation).

### `database.py`

- `create_connection(path)` — opens SQLite with `check_same_thread=False` and
  `sqlite3.Row` rows.
- `init_schema(connection)` — creates the `threads` and `notes` tables.
- `THREADS_TABLE_SCHEMA`, `NOTES_TABLE_SCHEMA` — the DDL in one place each.

### `models.py`

- `Thread` — frozen dataclass: `thread_id`, `title`, `created_at`,
  `updated_at`. Used by the repository, services, and CLI (and later Pydantic
  response schemas).
- `Note` — frozen dataclass: `note_id`, `thread_id`, `title`, `content`,
  `created_at`. Used by `NotesRepository` and the note tools.
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
- `mocks.py` — simulated implementations of common API-backed tools:
  `web_search`, `fetch_url`, `get_news`, `get_weather`, `get_stock_price`,
  `convert_currency`, `send_email`, `send_slack_message`,
  `create_calendar_event`, `list_calendar_events`, `translate_text`,
  `find_recipe`, `get_holidays`, `track_package`. Each response carries
  `"mock": true`; calendar events live in memory for the process lifetime.
  Replace a tool body with a real client call when its credentials are
  available — signatures and return shapes can stay the same.
- `registry.py` — `STATIC_TOOLS` (32 repository-free tools) plus
  `get_tools(notes_repository)`, which appends the four note tools for a total of
  36. `container.py` passes the result to both `create_llm` and `build_chatbot`.

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

Tools that need shared state (like notes) are built by a `create_*_tools()`
factory that closes over a repository, and `get_tools(repository)` includes them.
This keeps tools dependent only on their repository rather than on global state.

Mock tools are intentionally honest: JSON responses include `"mock": true`, no
network calls are made, and the modeled state (calendar) lives in module memory
for the process lifetime. Notes are the exception: they are durable SQLite rows.

### `cli.py`

Presentation only:

- `main()` builds the container, runs the loop, and always closes the connection
  in a `finally` block.
- On startup it restores the most recently updated thread, or creates one.
- Slash commands: `/new`, `/threads`, `/switch`, `/history`, `/rename`,
  `/delete`, `/help`, `/exit`.
- `process_message()` prints `Assistant: `, streams token events, renders
  `[tool]` / `[tool result: ...]` lines for tool activity (results truncated to
  200 chars), then prints the generated title if the `done` event carries one.
- Stream/LLM exceptions are caught and printed; `KeyboardInterrupt` and any
  other loop-level exceptions are handled without exiting.

`show_history` maps LangChain message types (`human`, `ai`, `system`) to display
roles and skips system messages.

---

## 6. Request/flow diagrams

### Sending a message

```text
User types text
      │
      ▼
cli.process_message(chat_service, thread_id, text)
      │
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
CLI prints tokens; prints title when done
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

### Creating / switching / deleting threads

```text
/new      → ThreadService.create_thread() → INSERT into threads
/threads  → ThreadService.list_threads()   → SELECT ordered by updated_at
/switch   → thread_exists? → set current_thread_id (no DB write)
/history  → ChatService.get_messages()     → checkpointer state
/rename   → ThreadService.rename_thread()  → UPDATE title, updated_at
/delete   → ThreadService.delete_thread()
              ├─ checkpointer.delete_thread(id)
              └─ repository.delete(id)
            if it was active → create a replacement thread
```

---

## 7. Persistence model

One SQLite database (`DATABASE_PATH`) holds three independent concerns:

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

### 7.3 Conversation state — owned by LangGraph

`SqliteSaver.setup()` creates and manages its own checkpoint tables
(`checkpoints`, checkpoint blobs/writes and migrations; exact names are
LangGraph-version dependent). These store the full message history per
`thread_id` and are **never** modified directly by application code — only
through the compiled graph and `checkpointer.delete_thread()`.

The split is deliberate:

- Metadata is cheap to query and render in a thread list.
- Notes are small durable records, independent of any conversation.
- Message history is managed by the checkpointer so LangGraph can replay and
  resume graph state.

Because all three share one connection, `delete_thread` removes checkpoints and
metadata together while leaving notes intact.

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
_run_interactive()
      ├─ restore latest thread or create one
      ├─ input loop (commands / chat)
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
2. → `cli.main()` → `build_container()`
3. → `_run_interactive()` → input loop

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

The CLI maps this to `print()`. A future SSE endpoint maps it to:

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
(CLI prints them, an API would emit `event: error` and a 4xx/5xx as appropriate).

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
- **Agents / more routing** — add nodes in `graph/nodes.py` and edges in
  `graph/workflow.py`; `ChatService` is unchanged.
- **Different database** — change `database.py` and `repository.py`; services and
  CLI stay the same.
- **Different model/provider** — change `llm.py` only.
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
10. **Every tool schema is sent to the model on every call** — 36 tools increase
    prompt size and can slow tool selection. Trim `STATIC_TOOLS` (or gate tools
    by config) if latency or cost matters.

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
```

Run the suite with:

```bash
uv run pytest
```

Tests use `tmp_path` SQLite databases plus fake graph, LLM, title, thread, and
checkpointer doubles (`tests/fakes.py`), so no OpenAI calls are made. Coverage
includes configuration precedence, container wiring and schema creation, thread
service CRUD and ordering, checkpoint cleanup on delete, `ChatService`
streaming/title behavior and tool-event emission, the real `ToolNode` loop, every
tool implementation (core, utilities, life, notes, mocks), notes persistence
across separate SQLite connections, thread isolation of notes, schema migration
for legacy note tables, CLI output and the interactive command loop, and package
entry points.

Manual tool checks in the CLI:

```text
What's the monthly payment on a 250000 loan at 6% for 30 years?
Convert 100 USD to EUR.
Save a note titled "groceries" with milk and eggs.
What time is 12:00 UTC in Asia/Dhaka?
What's the weather in Dhaka?
```

Expect a `[tool]` line, a `[tool result: ...]` line, then the answer. Mock
results include `"mock": true`.
