# Agentic AI Chatbot

A hands-on project for learning and building an **Agentic AI Chatbot** with Python,
LangChain, and LangGraph.

The application is currently a modular, interactive **CLI**. It preserves
thread-isolated conversations in SQLite through LangGraph's `SqliteSaver`,
generates conversation titles automatically, streams model responses token by
token, and supports tool calling through a LangGraph tool loop. It also performs
**retrieval-augmented generation** over local Markdown, text, and PDF files,
using OpenAI embeddings and one FAISS index per namespace. Optional LangSmith
tracing sends runs to LangSmith for debugging and monitoring. The code is split
into presentation, service, graph, retrieval, and persistence layers so a
FastAPI backend can be added later without rewriting business logic.

The terminal experience is a premium **emerald-grid** interface built with
**Rich** and **prompt_toolkit**: a framed welcome hero with a neural-network grid
backdrop and live runtime status, a `/` command menu with descriptions, Tab
completion (including thread IDs), contextual help, fuzzy suggestions for typos,
and Markdown rendering for structured answers. Colours and typography are
centralised in a single design system (`cli/theme.py`) so the whole interface
shares one emerald identity.

For the full design and migration plan, see [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Project Goals

- Build an AI-powered conversational chatbot.
- Understand the fundamentals of Agentic AI.
- Explore LangChain and LangGraph through practical implementation.
- Preserve conversation history and thread isolation with SQLite.
- Keep business logic framework-agnostic so it is reusable by a CLI or an API.
- Provide a tool-calling loop with a single registry of local and mock-backed tools.
- Add retrieval-augmented generation over local documents with per-namespace
  vector indexes and page-level PDF citations.
- Add a FastAPI backend and frontend later without restructuring the core.

## Tech Stack

| Technology                        | Purpose                                  |
| --------------------------------- | ---------------------------------------- |
| **Python**                        | Primary language                         |
| **LangChain**                     | LLM application development              |
| **LangGraph**                     | Graph-based workflow orchestration       |
| **LangGraph SQLite Checkpointer** | Conversation state persistence           |
| **LangSmith**                     | Tracing and observability                |
| **OpenAI**                        | Chat models and `text-embedding-3-small` embeddings |
| **FAISS**                         | One vector index per namespace (RAG)     |
| **pypdf**                         | PDF text extraction (no OCR)             |
| **Pydantic / pydantic-settings**  | Configuration loading and validation     |
| **Rich**                          | Terminal panels, tables, Markdown, color |
| **prompt_toolkit**                | Input, autocomplete, history, shortcuts  |
| **SQLite**                        | Threads, notes, document text/metadata, checkpoints |
| **uv**                            | Package and project management           |
| **FastAPI / Uvicorn**             | Planned HTTP layer (not implemented yet) |
| **pytest**                        | Automated tests (no OpenAI calls)        |

## Project Structure

```text
agentic-chatbot/
├── ARCHITECTURE.md              # Detailed architecture and FastAPI migration plan
├── README.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── chatbot_memory.db            # SQLite: thread metadata + LangGraph checkpoints
├── docs/                        # Documents indexed by /ingest
├── data/faiss/                  # One FAISS index file per namespace
│
├── src/
│   └── agentic_chatbot/
│       ├── __init__.py          # Exposes main() for the console script
│       ├── __main__.py          # python -m agentic_chatbot entry point
│       ├── config.py            # settings + LangSmith env export
│       ├── container.py         # Composition root (wires all resources)
│       ├── llm.py               # ChatOpenAI factory
│       ├── embeddings.py        # OpenAIEmbeddings factory
│       ├── loaders.py           # text/Markdown/PDF -> page-aware sections
│       ├── vector_store.py      # per-namespace FAISS indexes
│       ├── database.py          # SQLite connection + schema
│       ├── models.py            # Thread, Note, Document, TurnEvent dataclasses
│       ├── repository.py        # Thread, Notes, and Documents repositories
│       │
│       ├── cli/                 # Terminal presentation (Rich + prompt_toolkit)
│       │   ├── __init__.py      # public exports: main, run_session, dispatch
│       │   ├── theme.py         # design system: emerald palette + surfaces
│       │   ├── glyphs.py        # terminal-safe symbol fallback
│       │   ├── background.py    # emerald grid + neural-node decoration
│       │   ├── console.py       # Rich rendering (hero, messages, commands)
│       │   ├── chat.py          # streaming turns + tool timing + status
│       │   ├── commands.py      # single command table + handlers + dispatch
│       │   ├── registry.py      # Command record, lookup, fuzzy matching
│       │   ├── session.py       # per-run state shared by handlers
│       │   ├── input.py         # framed prompt + prompt_toolkit completion
│       │   └── app.py           # interactive loop + main()
│       │
│       ├── graph/
│       │   ├── state.py         # ChatState
│       │   ├── nodes.py         # chat node
│       │   └── workflow.py      # compiled LangGraph (chat ⇄ tools)
│       ├── services/
│       │   ├── chat_service.py   # streaming turns + history
│       │   ├── thread_service.py # thread lifecycle
│       │   ├── title_service.py  # automatic titles
│       │   └── document_service.py # ingestion, chunking, retrieval
│       └── tools/
│           ├── builtin.py        # calculator, get_current_time
│           ├── utilities.py      # local helpers (hash, base64, units, ...)
│           ├── life.py           # loan, tip, BMI, age, timezone, fuel
│           ├── notes.py          # database-backed note tools
│           ├── documents.py      # search_documents / list_documents
│           ├── mocks.py          # mocked API tools (weather, search, ...)
│           └── registry.py       # STATIC_TOOLS / get_tools(repo, documents)
│
├── tests/                       # Pytest suite (fakes + temporary SQLite)
├── notebooks/                   # Learning notebooks
└── data/                        # Local database + FAISS index files
```

## Architecture Summary

The application follows a one-way dependency flow:

```text
cli/  →  container.py  →  services  →  graph / repository / retrieval  →  SQLite + FAISS
```

- **Presentation** (`cli/`) — reads input and renders output only. No
  conversation logic, SQL, or graph code lives here.
- **Services** (`services/`) — chat orchestration, thread lifecycle, titles, and
  document ingestion/retrieval. Independent of any UI or HTTP framework.
- **Graph** (`graph/`) — LangGraph state, the chat node, the `ToolNode`, and the
  compiled chatbot.
- **Retrieval** (`loaders.py`, `vector_store.py`, `embeddings.py`) — text/PDF
  loading, chunk embeddings, and one FAISS index per namespace.
- **Tools** (`tools/`) — `@tool` implementations registered in `registry.py` and
  executed by LangGraph's `ToolNode`, including `search_documents`.
- **Persistence** (`repository.py`, `database.py`) — thread, note, and document
  metadata/text SQL. Vectors are not stored in SQLite.
- **Checkpointer** — `SqliteSaver` stores conversation messages and graph state.
- **Container** (`container.py`) — builds and owns the SQLite connection,
  checkpointer, LLM, embeddings, vector store, document service, tool-bound LLM,
  compiled graph, and services.

`ARCHITECTURE.md` explains each module, the request flow, the streaming event
contract, and the exact steps to add FastAPI later.

## Installation

This project uses [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/developerbayazid/agentic-chatbot.git
cd agentic-chatbot

uv sync
```

## Environment Configuration

Create a `.env` file from the template:

```bash
cp .env.example .env
```

Required:

```env
OPENAI_API_KEY=your_openai_api_key
```

Optional (defaults shown):

```env
DATABASE_PATH=chatbot_memory.db
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.0
SYSTEM_PROMPT=You are a helpful AI assistant.
```

Optional retrieval / RAG settings (defaults shown):

```env
EMBEDDINGS_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
RAG_CHUNK_SIZE=800
RAG_CHUNK_OVERLAP=120
RAG_TOP_K=4
RAG_MIN_SCORE=0.15
DOCS_PATH=docs
RAG_INDEX_PATH=data/faiss
RAG_MAX_TEXT_BYTES=2000000
RAG_MAX_PDF_BYTES=20000000
RAG_MAX_PDF_PAGES=200
```

Optional LangSmith tracing (defaults shown):

```env
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=agentic-chatbot
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

Notes:

- `DATABASE_PATH` defaults to `chatbot_memory.db` in the current directory.
- An existing `chatbot_memory.db` is reused as-is; the schema matches previous
  versions of the project.
- `LANGSMITH_TRACING=true` with `LANGSMITH_API_KEY` set enables tracing. See
  [Observability with LangSmith](#observability-with-langsmith).
- Variables already set in the OS environment take precedence over `.env`.
- `.env` is ignored by Git. Never commit API keys.

## Running the Chatbot

Activating the virtual environment is optional; `uv run` uses it automatically.

```bash
uv run agentic-chatbot
```

Or through the package module entry point:

```bash
uv run python -m agentic_chatbot
```

Both commands start the interactive CLI. On startup it restores the most recently
updated conversation, or creates a new one.

The console script is declared in `pyproject.toml`:

```toml
[project.scripts]
agentic-chatbot = "agentic_chatbot:main"
```

## The Terminal Interface

The interface uses a **premium emerald-grid** identity: a deep dark background, a
subtle geometric grid with neural-network nodes, and a single emerald accent
(`#10B981`) reserved for identity and interactive elements. Colours, typography,
and surfaces are centralised in `cli/theme.py`; no component hardcodes a colour.
The layout is left-aligned and readable, with a framed hero on startup and a
framed composer for input.

```text
╭──────────────────────────────────────────────────────╮
│ ●───────┼───────┼───────┼───────┼───────┼───────●─── │
│ │       │       │       │       │       │       │    │
│                      BAYAZID AI                      │
│                                                      │
│                Personal AI Assistant                 │
│ │       │       │       │       │       │       │    │
│ ●───────●───────┼───────┼───────┼───────┼───────┼─── │
╰──────────────────────────────────────────────────────╯
  Your intelligent workspace.   ·   v0.1.0

  ● MODEL    gpt-4o-mini       ● STORAGE  SQLite · connected
  ● GRAPH    ready             ● TRACING  on
  ● TOOLS    37                ● SESSION  0367932

  /help commands  ·  /threads conversations  ·  /new new conversation

  /help for commands  ·  /exit to quit
```

The hero frames the brand lockup over a neural-network grid. The grid strokes are
a very dark green so they read as texture rather than noise, and the title is
stamped on a cleared row so text never sits on a background character. Below the
hero, emerald status bullets report the model, storage health, graph state,
tracing state, tool count, and a short session ID — every one a real runtime
fact. `/status` shows a detailed readout instead, including the database path and
its health check. Neither surface prints API keys or other secrets.

The composer is a framed prompt — a top rule, a left rail, and an emerald `❯` —
with a slim status bar underneath that tracks the model, short thread ID,
directory, and keybindings:

```text
  ──────────────────────────────────────────────────────
  │ ❯ Ask me anything…
  gpt-4o-mini · 03679327 · agentic-chatbot · /help · enter send · ctrl+d exit
```

### Transcript grammar

Each message is labelled and tool activity is marked as it happens, using the
real LangGraph event stream:

| Marker | Row |
| ------ | --- |
| `YOU` | your message |
| `BAYAZID AI` | the assistant's reply, streamed live or rendered as Markdown |
| `● Executing tool: <name> · running` | a tool call, announced when it starts |
| `✓ Completed · 0.3s` | a tool result, with measured elapsed time |
| `✗ Failed` | a failed tool or error, printed inline so it stays selectable |

```text
YOU
What's the weather in Dhaka?

BAYAZID AI
Let me check that for you.
  ● Executing tool: get_weather  ● running
    ✓ Completed · 0.3s
It is currently 27°C and clear in Dhaka.
```

A status bar under the composer tracks the model, short thread ID, working
directory, `/help`, and the active keybindings. The message transcript is
left-aligned plain rows — no heavy boxes around every message — so resizing the
window cannot garble earlier output. The hero's box drawing degrades with Unicode
support, and every literal glyph falls back to an ASCII equivalent on terminals
that cannot encode it (`●`→`*`, `✓`→`+`, `❯`→`>`, `✗`→`x`).

### Command menu and completion

Typing `/` lists every command with its description; typing a partial command
narrows the list. Tab accepts the highlighted suggestion, Up/Down move through
the menu and input history.

```text
❯ /th
  /threads       List all conversations
```

`/delete` completes thread IDs from the database, with each conversation title
shown beside the ID:

```text
❯ /delete ab
  ab12f0c3-...   Weekly planning
  ab98d771-...   Receipt questions
```

### Session picker

`/threads` opens an interactive picker: a search box over a live table of
conversations showing recency, message count, and a `●` marker on the active
thread. Type to filter, `Up`/`Down` to move, `Enter` to switch, `Esc` to cancel.

```text
› Type to search sessions…
─────────────────────────────────────────────────────────────
  #   Modified   Git Branch  Messages  Summary
  1.  18h ago    -               270  Terminal UI Redesign  ●
› 2.  19h ago    -               817  Business Analytics Tools
  3.  1d ago     -               224  Tool Integration Plan

  ↑/↓ move  ·  Enter open  ·  Esc cancel
```

On terminals where prompt_toolkit cannot attach (piped input, CI), `/threads`
falls back to the plain static list.

### Keyboard shortcuts

| Shortcut       | Action                                       |
| -------------- | -------------------------------------------- |
| `Tab`          | Accept the selected completion               |
| `Up` / `Down`  | Navigate suggestions and input history       |
| `Enter`        | Submit input                                 |
| `Ctrl+C`       | Interrupt input and continue chatting        |
| `Ctrl+D`       | Exit on an empty line                        |

`Ctrl+C` during a response stops that turn; the session and its history remain
intact. The loop keeps running until `/exit` or `Ctrl+D`.

### Rendering

User messages, assistant answers, tool activity, notices, and errors each have a
distinct visual treatment:

```text
YOU
What's the weather in Dhaka?

BAYAZID AI
Let me check that for you.
  ● Executing tool: get_weather  ● running
    ✓ Completed · 0.3s
It is currently 27°C in Dhaka.

  Conversation title: Weather in Dhaka
```

Plain prose streams token by token as the model produces it. When a response
starts a Markdown block (heading, list, table, code fence), the text is buffered
and rendered with Rich so structure is preserved instead of appearing as raw
symbols. Tool calls and results are announced as they happen — a call is shown as
`● Executing tool: …`, and its result reports `✓ Completed` or `✗ Failed` with the
measured elapsed time. Nothing is fabricated: only operations that actually run
are shown.

### Terminal compatibility

The emerald palette is emitted as truecolor where available and downgrades
gracefully otherwise. The hero's rounded box and the grid's box/node characters
degrade with Unicode support (rounded → square → ASCII), and literal symbols
(bullet, check mark, prompt, arrow) are chosen at startup from the console
encoding so the UI stays readable on legacy Windows code pages instead of raising
`UnicodeEncodeError`. The framed composer tracks terminal resizes. If
prompt_toolkit cannot attach to a console at all (piped input, CI, some legacy
shells), the CLI falls back to a plain prompt with the same commands.

## CLI Commands

Every command is defined once in `src/agentic_chatbot/cli/commands.py`. That
table drives execution, the `/` menu, Tab completion, `/help`, and typo
suggestions.

| Command    | Description                                | Category     |
| ---------- | ------------------------------------------ | ------------ |
| `/help`    | Show commands, or details for one command  | General      |
| `/clear`   | Clear the terminal screen                  | General      |
| `/status`  | Show model, database, graph, and tracing   | General      |
| `/ingest`  | Index Markdown, text, and PDF files        | General      |
| `/documents` | List indexed documents and namespaces    | General      |
| `/version` | Show the application version               | General      |
| `/exit`    | Exit the chatbot                           | General      |
| `/new`     | Create a new conversation                   | Conversation |
| `/threads` | Open the session picker to switch          | Conversation |
| `/history` | Show the current conversation history      | Conversation |
| `/rename`  | Rename the current conversation            | Conversation |
| `/delete`  | Delete a conversation and its checkpoints  | Conversation |
| _anything else_ | Send a chat message                   | —            |

`/help <command>` explains one command:

```text
❯ /help delete

  /delete   Delete a conversation and its messages

  USAGE      /delete [thread_id]
  ARGUMENTS  Thread ID. Omit to pick from the picker; tab-completes
             existing conversations.
  EXAMPLE    /delete 3f2c1b9a-7d4e-4c1a-9f2b-0a1b2c3d4e5f
  BEHAVIOUR  Opens the session picker (or takes a thread ID), confirms,
             then deletes checkpoints and metadata.
```

`/rename` prompts for its argument when omitted, and a bare `/delete` opens the
picker to choose what to remove. `/clear` only clears the screen; it
never deletes messages, and conversation history is unaffected.

### Unknown commands

Slash input is never forwarded to the LLM. A typo produces a scored suggestion
instead:

```text
❯ /threds

  Unknown command: /threds
  Did you mean?
    /threads   List all conversations
```

Ordinary text (anything not starting with `/`) is still sent to the LangGraph
agent exactly as before.

### Adding a command

`COMMANDS` in `src/agentic_chatbot/cli/commands.py` is the single source of truth.
Append one `Command` and execution, the `/` menu, Tab completion, `/help`, and
typo suggestions all include it automatically.

```python
def _models(session: ChatSession, argument: str) -> None:
    ui.document(session.console, "Model", session.settings.llm_model)


Command(
    name="/models",
    description="Show the configured model",
    category=CATEGORY_GENERAL,
    usage="/models",
    example="/models",
    behavior="Prints the model name from settings.",
    arguments="None.",
    handler=_models,
)
```

Guidelines:

- Put handlers in `commands.py`; keep rendering in `console.py`.
- Never read or write the database directly — call `session.thread_service` or
  `session.chat_service`.
- Use `ui.*` helpers for output so styling stays consistent.
- For argument completion, add an `arg_completer` returning real data (see
  `_thread_ids`); never hardcode IDs.
- Add the name to `CATEGORY_GENERAL` or `CATEGORY_CONVERSATION` so it appears in
  the right help section.

## Tools

The tool-bound LLM receives every schema returned by
`get_tools(notes_repository, document_service)`. When it emits tool calls,
LangGraph's `ToolNode` executes them and routes back to the chat node for a final
answer. Tool activity is printed as it happens:

```text
BAYAZID AI
  ● Executing tool: get_weather  ● running
    ✓ Completed · 0.3s
It is currently 27°C in Dhaka.
```

Selection is intent-driven. The system prompt includes a tool-selection policy
and each description states when it applies: general-knowledge questions are
answered directly, while references to your documents, uploads, or saved notes
require the matching tool. Empty results and tool errors are reported honestly
instead of being guessed around. On the first turn of each conversation the
system prompt also lists the indexed documents, so personal identity and profile
questions ("Who is Bayazid Hasan?") can trigger `search_documents` even without
saying "my documents" — while unrelated general knowledge still answers
directly.

### Registered tools (37)

| Category            | Module         | Tools                                                                                                                                                                                                 |
| ------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Core                | `builtin.py`   | `calculator`, `get_current_time`                                                                                                                                                                      |
| Local utilities     | `utilities.py` | `convert_units`, `generate_uuid`, `generate_password`, `hash_text`, `base64_encode`, `base64_decode`, `format_json`, `regex_search`, `summarize_text`                                                 |
| Everyday life       | `life.py`      | `calculate_loan_payment`, `calculate_tip_split`, `calculate_bmi`, `calculate_age`, `days_between`, `convert_timezone`, `estimate_fuel_cost`                                                            |
| Notes (per thread)  | `notes.py`     | `save_note`, `list_notes`, `search_notes`, `delete_note` — scoped to the active conversation                                                                                                           |
| Retrieval (RAG)     | `documents.py` | `search_documents`, `list_documents` — cosine search over ingested text and PDFs, one FAISS index per namespace                                                                                        |
| Mock API services   | `mocks.py`     | `fetch_url`, `get_news`, `get_weather`, `get_stock_price`, `convert_currency`, `send_email`, `send_slack_message`, `create_calendar_event`, `list_calendar_events`, `translate_text`, `find_recipe`, `get_holidays`, `track_package` (`web_search` is defined but currently disabled) |

All tools that need an external service (`mocks.py`) return simulated data and
include `"mock": true` in their JSON. They make **no network calls** and need no
keys. Calendar events are stored in memory for the life of the process, while
notes are persisted in the SQLite database (`notes` table) and scoped to the
active `thread_id`: each conversation can only see and modify its own notes.
Replace a tool body with a real client call when credentials are available — the
signature and return shape can stay the same.

### Adding a tool

```python
from langchain_core.tools import tool

@tool
def word_count(text: str) -> str:
    """Count the words in a text."""  # the model uses this description
    return str(len(text.split()))
```

Then append `word_count` to `STATIC_TOOLS` in
`src/agentic_chatbot/tools/registry.py`. `create_llm` and `ToolNode` pick it up
automatically; no graph, service, or CLI changes are needed. Tools that need
shared state (notes, retrieval) are built by a `create_*_tools()` factory and
returned from `get_tools(notes_repository, document_service)` instead.

### Example prompts

- "What's the monthly payment on a $250,000 mortgage at 6.5% for 30 years?"
- "Split a $120 dinner bill with an 18% tip across 4 people."
- "My weight is 70 kg and I'm 1.75 m tall — what's my BMI?"
- "What time is 12:00 UTC in Asia/Dhaka?"
- "How many business days between 2026-11-01 and 2026-12-15?"
- "Save a note titled 'Grocery list' with milk, eggs, and spinach."
- "Search my notes for 'spinach'." (notes are private to the current thread)
- "What's the weather in Dhaka?" / "Find a recipe for chicken curry."
- "What are the public holidays in Bangladesh in 2027?"
- "Track my package AB123456789."
- "Convert 250 USD to BDT."
- "Create a calendar event 'Design review' on 2026-12-01 at 10:00 for 45 minutes."
- "Search the web for LangGraph tool calling best practices."
- "According to my handbook, what's the onboarding process?" (after `/ingest`)
- "What does the policy PDF say about page 4?"

## Knowledge Base (RAG)

Supported files: `.md`, `.markdown`, `.txt`, `.rst`, and `.pdf`. Drop them in
`docs/` (or any folder) and index them:

```text
/ingest docs handbook          # index docs/ into the "handbook" namespace
/documents                     # list namespaces and indexed files
/ingest docs policies --force  # re-embed and rebuild the index
```

Each namespace has its own FAISS index file under `data/faiss/`. Text files use
one section; PDFs are split per page so results cite a page number. Unchanged
files are skipped by content hash; `--force` overrides that. `search_documents`
is exposed to the model, which calls it for questions about the ingested
material and cites title/source/page.

Notes:

- Scanned/image-only PDFs have no text layer and are reported as ingest errors —
  there is no OCR.
- `RAG_MIN_SCORE` (default `0.15`) filters weak hits so "nothing relevant" is a
  real answer instead of the nearest unrelated chunk.
- A search `namespace` must be a value from `/documents` (the ingest namespace),
  not a document title. An unknown namespace returns an error listing the valid
  ones; omitting it searches everything.
- Changing `EMBEDDINGS_MODEL` or `EMBEDDING_DIMENSIONS` invalidates existing
  indexes; re-ingest with `--force` after clearing `data/faiss/`.

## Streaming

`ChatService.stream_turn()` yields transport-neutral events:

- `TurnEvent(type="token", content="...")` for each streamed chunk.
- `TurnEvent(type="tool_call", name=..., content="...")` when the model requests
  a tool; `content` holds the JSON arguments.
- `TurnEvent(type="tool_result", name=..., content="...")` when that tool
  returns; `content` holds the result.
- `TurnEvent(type="done", title=...)` when the turn is persisted; `title` is set
  only when a new title was generated on the first turn.

The CLI prints these events directly (`● Executing tool: …` / `✓ Completed`
lines for tool activity). A future SSE endpoint can map the same events to `event: token` /
`event: tool_call` / `event: tool_result` / `event: done` without changing the
service.

## Observability with LangSmith

Tracing is off by default. Set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in
`.env` to send each run to LangSmith. `LANGSMITH_PROJECT` selects the project
(default `agentic-chatbot`), and `LANGSMITH_ENDPOINT` targets a self-hosted
instance when set (default `https://api.smith.langchain.com`).

LangChain and LangSmith read tracing configuration from the process environment,
not from the `Settings` object. `get_settings()` therefore exports the
`langsmith_*` settings into `os.environ` before the LLM and graph are created, so
`.env` values take effect for both `uv run agentic-chatbot` and
`uv run python -m agentic_chatbot`. Values already present in the OS environment
are not overwritten.

## SQLite Persistence

One SQLite database holds four independent concerns:

1. **Thread metadata** — the `threads` table (`thread_id`, `title`,
   `created_at`, `updated_at`), managed by `ThreadRepository`.
2. **Notes** — the `notes` table (`note_id`, `thread_id`, `title`, `content`,
   `created_at`), managed by `NotesRepository`. Notes survive restarts and are
   private to the conversation that created them.
3. **Knowledge base** — the `documents` and `document_chunks` tables hold
   document text and metadata, and `rag_meta` records the embedding dimension.
   Vectors are **not** in SQLite: each namespace has its own FAISS index under
   `RAG_INDEX_PATH` (`data/faiss/`), keyed by `document_chunks.row_id`.
4. **Conversation state** — LangGraph checkpoint tables created and managed by
   `SqliteSaver.setup()`.

Deleting a thread removes its checkpoints first, then its metadata. Deleting a
thread while it is active creates a replacement conversation. Notes and
documents are kept until explicitly deleted, and notes are only visible from
their own thread. Deleting a thread does not delete its notes or documents.

Back up `data/faiss/` together with the database, or rebuild it after a loss
with `/ingest docs <namespace> --force`.

## Running Tests

```bash
uv run pytest
```

The suite uses temporary SQLite databases and fake graph/LLM implementations, so
it never calls the OpenAI API and never touches `chatbot_memory.db`. It covers
configuration precedence, container wiring and schema creation, thread lifecycle
and ordering, checkpoint cleanup on delete, streaming and title generation, tool
execution and event emission, the individual tool implementations (calculators,
utilities, notes, documents, and mocks), notes persistence across SQLite
connections, document ingestion (text and PDF), per-namespace FAISS indexing and
retrieval, CLI rendering, the interactive command loop, and package entry points.

The CLI has dedicated coverage across these test files:

| Test file                        | Covers                                                         |
| -------------------------------- | -------------------------------------------------------------- |
| `test_cli_registry.py`           | command lookup, normalization, grouping, prefix and fuzzy match |
| `test_cli_commands.py`           | the command table, dispatch routing, and every handler          |
| `test_cli_chat.py`               | streaming, tool visibility, Markdown detection, error display   |
| `test_cli_input.py`              | completion logic, glyph fallback, loop behavior, input routing  |
| `test_cli_prompt_integration.py` | real `PromptSession` Tab completion for commands and arguments  |
| `test_cli_banner.py`             | emerald theme, the framed welcome hero, and the status readout  |
| `test_cli_rendering.py`          | background grid, framed input, and timed tool feedback          |
| `test_cli_picker.py`             | session picker: timing, filtering, selection, keyboard drive    |

RAG-specific tests:

| Test file                        | Covers                                                         |
| -------------------------------- | -------------------------------------------------------------- |
| `test_loaders.py`                | text normalization, PDF pages/encryption/scanned/truncation     |
| `test_vector_store.py`           | per-namespace index files, isolation, merge, remove, persistence |
| `test_documents_repository.py`   | document/chunk SQL, page round-trip, delete, schema guards      |
| `test_document_service.py`       | ingest, dedupe, `force`, limits, compensation on index failure   |
| `test_document_tools.py`         | tool JSON shapes and error strings                              |

Notable assertions: unknown slash commands are never forwarded to the LLM, plain
text always is, secrets never appear in status output, and both the
prompt_toolkit and plain-input paths stay usable.

```bash
# Optional: byte-compile the package
uv run python -m compileall -q src/agentic_chatbot
```

## Learning Progress

- [x] Initial project setup
- [x] Basic LLM integration
- [x] Chatbot implementation
- [x] Conversation history management
- [x] State management
- [x] LangGraph integration
- [x] Checkpointing and persistence
- [x] SQLite database integration
- [x] Multiple conversation thread support
- [x] Automatic conversation title generation
- [x] Conversation history restoration
- [x] Thread switching
- [x] Thread renaming
- [x] Thread deletion
- [x] Streaming LLM responses
- [x] Modular, layered project structure
- [x] Automated test suite
- [x] LangSmith observability and tracing
- [x] Tool calling and integration
- [x] Professional terminal UI (Rich + prompt_toolkit)
- [x] Emerald-grid design system with neural-network background
- [x] Command registry with autocomplete, help, and fuzzy suggestions
- [x] Retrieval-augmented generation (FAISS, one index per namespace)
- [x] PDF ingestion with page-level citations
- [ ] FastAPI backend integration
- [ ] Agentic decision-making
- [ ] Cross-thread memory management
- [ ] Advanced agentic workflows
- [ ] Frontend integration

## Current Status

The modular CLI is operational with a polished emerald-grid terminal interface.
Conversation threads, automatic titles, history, streaming, tool calling, and
SQLite persistence all run through the service layer under
`src/agentic_chatbot/`. The presentation layer is a `cli/` package: a centralised
emerald design system (`theme.py`), an emerald-grid background renderer
(`background.py`), a Rich renderer, a prompt_toolkit input layer, and one command
table. Thirty-seven tools are registered in
`src/agentic_chatbot/tools/` — local utilities, retrieval over ingested text and
PDFs, and mock implementations of common API-backed tools (weather, search,
email, calendar, currency, …) that return `"mock": true` data until real
credentials are configured. Notes are stored in SQLite per conversation, so they
survive restarts and stay private to each thread. Documents are ingested with
`/ingest` (Markdown, text, reStructuredText, PDF), embedded with OpenAI, and
searched through one FAISS index per namespace. Add a tool to `registry.py` to
expose it to the model, or a command to `cli/commands.py` to expose it to the
user. LangSmith tracing is available when enabled through `.env`. FastAPI is not
part of the current runtime; it is the next planned milestone, and
`ARCHITECTURE.md` documents how to wire it in without touching the services.
