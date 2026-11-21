# Agentic AI Chatbot

An **agentic AI assistant** with three presentations over one core: a terminal
**CLI**, a **REST API** (FastAPI), and a **web app** (Next.js). It streams replies
token by token, calls tools through a LangGraph loop, performs retrieval-augmented
generation over your documents, and pauses for **human approval** before any
sensitive action runs.

Storage is **PostgreSQL**, the only backend: threads, notes, documents, chunk
embeddings (`pgvector` with an HNSW index), and LangGraph conversation checkpoints
all live in one database.

The web app is a **single-page application**: one document, client-side
navigation, an HttpOnly-cookie session, and a black-and-white interface modelled
on ChatGPT's layout — a date-grouped conversation sidebar, a slash-command
composer, and a live tool-activity timeline.

> Deploying? Start with [`POSTGRES.md`](./POSTGRES.md) for the database and
> [`API.md`](./API.md) for the REST contract. Design notes are in
> [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## What it does

- **Conversations** — thread-isolated history, automatic titles, token streaming,
  and resumable state.
- **Retrieval (RAG)** — Markdown, text, and PDF files are chunked, embedded, and
  stored in PostgreSQL. Hybrid search fuses vector similarity with BM25 keyword
  matching via Reciprocal Rank Fusion. Retrieval is **scoped to the caller**: the
  owner filter runs inside each retriever _before_ fusion, so another user's
  chunk can neither be returned nor influence the ranking of an authorised one.
- **Tools** — 91 tools, 15 of which are approval-gated. `GET /api/v1/tools`
  publishes the catalog, and the `requires_approval` flag is read from the same
  policy the graph enforces.
- **Human in the loop** — a sensitive action interrupts the graph; an approval is
  bound to that specific interrupt, so a stale, replayed, or concurrently
  submitted decision is refused rather than executed twice.
- **ERP demo domain** — products, stock, customers, sales, invoices, and purchase
  orders over one inspectable JSON dataset. It is a _demo dataset for the tools_,
  deliberately not a dashboard, and it is not part of the database migration.

For the full design, see [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Project Goals

- Build an AI-powered conversational chatbot.
- Understand the fundamentals of Agentic AI.
- Explore LangChain and LangGraph through practical implementation.
- Preserve conversation history and thread isolation.
- Keep business logic framework-agnostic so it is reusable by the CLI, the API,
  and the web app.
- Provide a tool-calling loop with a single registry of local and mock-backed tools.
- Add retrieval-augmented generation with page-level PDF citations and hybrid
  fusion for better recall.
- Add an ERP-style inventory domain that demonstrates realistic business
  workflows over JSON data without introducing an ORM.
- Practise Human-in-the-Loop with LangGraph interrupts, resume, argument editing,
  approval/rejection, checkpoint persistence, and idempotent side effects.
- Ship one service with three presentations, not three copies of the logic.

## Tech Stack

| Technology                             | Purpose                                             |
| -------------------------------------- | --------------------------------------------------- |
| **Python**                             | Primary language                                    |
| **LangChain / LangGraph**              | LLM application and graph orchestration             |
| **PostgreSQL 18**                      | Threads, notes, documents, chunks, checkpoints      |
| **pgvector**                           | Embedding column + HNSW index                       |
| **LangGraph Postgres Checkpointer**    | Conversation state persistence                      |
| **OpenAI**                             | Chat models and `text-embedding-3-small` embeddings |
| **rank-bm25**                          | Keyword index over document chunks                  |
| **pypdf**                              | PDF text extraction (no OCR)                        |
| **FastAPI / Uvicorn**                  | REST API over the same services                     |
| **Next.js 16 / React 19 / TypeScript** | Web application                                     |
| **Tailwind CSS 4**                     | Styling                                             |
| **TanStack Query / Zustand**           | Server state and UI state                           |
| **Pydantic / pydantic-settings**       | Configuration and validation                        |
| **Rich / prompt_toolkit**              | Terminal presentation                               |
| **uv / pnpm**                          | Python and Node package management                  |
| **pytest / Vitest**                    | Automated tests (no network calls)                  |

## Project Structure

```text
agentic-chatbot/
├── ARCHITECTURE.md              # How the system is built
├── API.md                       # REST contract
├── POSTGRES.md                  # Database, migration, pgvector
├── COMMAND-PARITY.md            # CLI commands vs. web, and exclusions
├── REVISED-ROADMAP.md           # Sprint plan and verification log
├── HITL.md                      # Human-in-the-loop design
├── README.md
├── main.py                      # `fastapi dev` entry point
├── pyproject.toml / uv.lock
├── .env.example
├── docs/                        # Documents indexed by the RAG tools
├── inventory-data/              # ERP demo dataset + pristine seed
│
├── src/agentic_chatbot/
│   ├── config.py                # settings (DSN, JWT, CORS, RAG)
│   ├── container.py             # composition root: one place that wires everything
│   ├── sql_backend.py           # minimal cursor adapter over psycopg
│   ├── postgres.py              # Postgres connection + schema
│   ├── postgres_schema.py       # tables, indexes, pgvector DDL
│   ├── pg_vector_store.py       # embeddings: pgvector with array fallback
│   ├── bm25_store.py            # BM25 index, rebuilt from SQL rows
│   ├── repository.py            # thread/notes/document repositories
│   ├── models.py                # domain dataclasses
│   │
│   ├── api/                     # REST presentation
│   │   ├── main.py              # create_app factory + middleware
│   │   ├── security.py          # JWT issue/verify, API-key exchange
│   │   ├── dependencies.py      # auth, container, settings dependencies
│   │   ├── routers/             # health, auth, chat, threads, approvals,
│   │   │                        #   documents, tools
│   │   └── schemas/             # strict request/response models
│   │
│   ├── cli/                     # terminal presentation (Rich + prompt_toolkit)
│   ├── graph/                   # LangGraph state, nodes, approval, workflow
│   ├── services/                # chat, thread, title, document
│   ├── inventory/               # ERP domain (JSON, no ORM), 54 tools
│   └── tools/                   # the remaining tool groups
│
├── frontend/                    # Next.js single-page application
│   └── src/
│       ├── app/                 # routes; (dashboard) holds the app shell
│       ├── components/          # layout, UI primitives
│       ├── features/            # chat, threads, documents, approvals,
│       │                        #   commands, nav, auth
│       ├── lib/api/             # the single HTTP client + SSE parser
│       └── stores/              # Zustand UI state
│
└── tests/                       # pytest suite (and frontend/ has Vitest)
```

## Quick start

```bash
# 1. Database. PostgreSQL is the default backend.
createdb bayazid
psql bayazid -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 2. Configure
cp .env.example .env        # set OPENAI_API_KEY, API_KEYS, JWT_SECRET_KEY

# 3. Run the API and the web app
uv run fastapi dev          # http://127.0.0.1:8000
cd frontend && pnpm install && pnpm dev   # http://localhost:3000

# …or use the CLI instead of the API
uv run agentic-chatbot
```

## Tests

```bash
uv run pytest                    # backend; needs the test database below
cd frontend && pnpm test && pnpm typecheck && pnpm lint
```

The suite runs against a real PostgreSQL server, because PostgreSQL is the only
backend. Each test creates and drops its own schema, so tests stay isolated
without a database per test. Point the suite at a server with
`TEST_POSTGRES_DSN` (defaults to
`postgresql://postgres:postgres@127.0.0.1:5432/agentic_chatbot_test`). The
database must exist and have the `vector` extension available. No network calls
are made: embeddings and the LLM are deterministic test doubles.

## Architecture Summary

One-way dependency flow, with three presentations over the same core:

```text
cli/  api/  frontend/  →  services  →  graph / repository / retrieval  →  PostgreSQL
```

- **Presentation** — `cli/` (terminal), `api/` (REST), `frontend/` (web app). Each
  reads input and renders output only. No conversation logic, SQL, or graph code
  lives in any of them.
- **Services** (`services/`) — chat orchestration, thread lifecycle, titles, and
  document ingestion/retrieval. Independent of any UI or HTTP framework.
- **Graph** (`graph/`) — LangGraph state, the chat node, the `ToolNode`, the HITL
  `approval` node, and the compiled chatbot.
- **Inventory** (`inventory/`) — JSON store, dataset validation, ERP business
  rules, sensitive-tool policy, and 54 grouped tools. Independent of the
  presentations and of the graph, which receives callbacks rather than imports.
- **Retrieval** — `loaders.py`, `embeddings.py`, `pg_vector_store.py`,
  `bm25_store.py`, `rrf.py`. Embeddings live in PostgreSQL with an HNSW index;
  BM25 is built in memory from SQL rows; RRF fuses the two rankings.
- **Tools** (`tools/`) — `@tool` implementations registered in `registry.py` and
  executed by LangGraph, including `search_documents` and the inventory set.
- **Persistence** — `repository.py` writes one portable SQL dialect through
  `sql_backend.py`, a thin cursor adapter over psycopg. `postgres_schema.py` owns
  the tables, indexes, and pgvector DDL.
- **Checkpointer** — `PostgresSaver` stores conversation messages and graph state,
  on the same connection as the relational data. Because that connection is not
  autocommit, the container's checkpointer commits after each write; without that,
  graph state would be rolled back when the connection closed.
- **Container** (`container.py`) — the single place that builds and owns the
  connection, checkpointer, LLM, embeddings, vector store, document service,
  tool-bound LLM, compiled graph, and services.

`ARCHITECTURE.md` explains each module, the request flow, and the streaming event
contract.

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
# PostgreSQL is the only backend — no default is shipped, because a connection
# string contains credentials. Set it in .env, never in source.
POSTGRES_DSN=postgresql://USER:PASSWORD@HOST:5432/DATABASE

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
RAG_SEARCH_MODE=hybrid
RAG_VECTOR_CANDIDATES=10
RAG_BM25_CANDIDATES=10
RAG_RRF_K=60
DOCS_PATH=docs
RAG_MAX_TEXT_BYTES=2000000
RAG_MAX_PDF_BYTES=20000000
RAG_MAX_PDF_PAGES=200
```

Optional REST API settings (defaults shown). Required only to serve HTTP:

```env
API_ENV=development                  # development | production
API_HOST=127.0.0.1
API_PORT=8000
API_UPLOAD_PATH=data/uploads
API_MAX_UPLOAD_BYTES=20000000
API_KEYS=alice=change-me-1,bob=change-me-2   # name=secret pairs
JWT_SECRET_KEY=                      # >= 32 chars; required in production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
CORS_ORIGINS=http://localhost:3000   # comma-separated, explicit origins
```

Optional inventory settings (defaults shown):

```env
INVENTORY_DATA_PATH=inventory-data/inventory/inventory_data.json
INVENTORY_OPERATOR_ID=EMP-006
INVENTORY_OPERATION_LOG_LIMIT=500
INVENTORY_AUDIT_LOG_LIMIT=1000
```

Optional LangSmith tracing (defaults shown):

```env
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=agentic-chatbot
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

Notes:

- `POSTGRES_DSN` is required and there is no default: without it the app refuses
  to start and says what to set. The schema is created on first start. See
  [`POSTGRES.md`](./POSTGRES.md).
- `INVENTORY_DATA_PATH` is cwd-relative. If the file is missing, the app still
  starts and logs a warning; inventory tools are simply not registered.
- `INVENTORY_OPERATOR_ID` maps the reviewer to an employee in the audit trail
  (default: Shirin Sultana, Finance Controller). An unknown ID falls back to
  `HUMAN_OPERATOR` and logs a warning.
- `INVENTORY_OPERATION_LOG_LIMIT` and `INVENTORY_AUDIT_LOG_LIMIT` keep only the
  newest log entries; older entries are dropped, not archived.
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
agentic-chatbot-api = "agentic_chatbot.api.main:main"
```

## REST API

The same services are also exposed over HTTP. The API is a second presentation
layer: it calls the same `ChatService`, `ThreadService`, `DocumentService`, and
compiled LangGraph the CLI drives, so nothing is duplicated.

**Full endpoint reference, payloads, error codes, and troubleshooting:
[`API.md`](./API.md).**

```bash
# from the project root, so .env and data/ resolve
uv run fastapi dev                         # FastAPI CLI, auto-reload (recommended)
uv run fastapi run                         # FastAPI CLI, production-style
uv run agentic-chatbot-api                 # uses API_HOST / API_PORT
# or explicitly
uv run uvicorn main:app --reload
uv run uvicorn --factory agentic_chatbot.api.main:create_app \
  --host 127.0.0.1 --port 8000
```

`fastapi dev` looks for `main.py`, `app.py`, or `api.py` in the **current
directory**, which is why the repository root has a one-line `main.py` that
exposes `app = create_app()`. It is the only file needed for that convenience —
the real application stays in `agentic_chatbot/api/`, and importing it opens no
database and compiles no graph (the lifespan does that).

Before any of these will serve an authenticated request, `.env` needs its API
settings (see below). Without `API_KEYS` and `JWT_SECRET_KEY` the app starts and
`/health` answers, but `/health/ready` reports **503** and every protected call
is `401`.

Swagger is at `/docs` and ReDoc at `/redoc` while `API_ENV=development`. Both are
disabled when `API_ENV=production`.

### Authentication

An operator exchanges a configured API key for a short-lived HS256 JWT. Keys are
declared with `API_KEYS=alice=secret,bob=secret`; use `secrets.token_urlsafe` for
both the keys and `JWT_SECRET_KEY` (at least 32 characters).

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/token \
  -H 'content-type: application/json' \
  -d '{"api_key":"change-me-1"}' | jq -r .access_token)
```

Every resource endpoint requires `Authorization: Bearer $TOKEN`. The token
subject is the caller's identity; it is never accepted from a request body.

### Endpoints

| Method | Path                              | Purpose                                                |
| ------ | --------------------------------- | ------------------------------------------------------ |
| GET    | `/health`                         | liveness: `{"status":"ok","application":"BAYAZID AI"}` |
| GET    | `/health/ready`                   | local readiness checks (200/503); no model call        |
| POST   | `/api/v1/auth/token`              | API key → access token                                 |
| POST   | `/api/v1/chat`                    | send a message, create or reuse a thread               |
| POST   | `/api/v1/chat/stream`             | the same turn as Server-Sent Events                    |
| GET    | `/api/v1/threads`                 | the caller's conversations                             |
| GET    | `/api/v1/threads/{id}`            | one conversation                                       |
| PATCH  | `/api/v1/threads/{id}`            | rename (`{"title": "..."}`)                            |
| DELETE | `/api/v1/threads/{id}`            | delete checkpoints, then metadata                      |
| GET    | `/api/v1/threads/{id}/history`    | conversational messages                                |
| GET    | `/api/v1/approvals`               | the caller's pending approvals                         |
| GET    | `/api/v1/approvals/{id}`          | approval detail incl. editable fields                  |
| POST   | `/api/v1/approvals/{id}/decision` | approve, edit, or reject                               |
| GET    | `/api/v1/documents`               | the caller's indexed documents                         |
| POST   | `/api/v1/documents`               | upload (multipart `file`) and index                    |
| GET    | `/api/v1/documents/{id}`          | document metadata                                      |
| DELETE | `/api/v1/documents/{id}`          | delete document + its vectors                          |

### Chat

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"message":"Hello, how are you?"}'
```

```json
{
    "thread_id": "0f9c…",
    "response": "Hello! How can I help you today?",
    "status": "completed",
    "title": "Simple Greetings",
    "approval_id": null
}
```

Pass `thread_id` to continue an existing conversation. A thread that does not
exist, or belongs to someone else, is `404 THREAD_NOT_FOUND` — the API never
confirms that another user's ID exists.

### Streaming

```bash
curl -N -X POST http://127.0.0.1:8000/api/v1/chat/stream \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"message":"Summarise the handbook"}'
```

```
event: thread            data: {"thread_id": "0f9c…"}
event: status            data: {"status": "processing"}
event: tool_start        data: {"tool": "search_documents", "arguments": {"query": "…"}}
event: tool_end          data: {"tool": "search_documents", "result": "…"}
event: token             data: {"content": "Hello"}
event: approval_required data: {"approval_id": "…", "thread_id": "…", "action": "update_product",
                                "title": "Update Product", "arguments": {…},
                                "allowed_decisions": ["approve", "edit", "reject"]}
event: final             data: {"title": "Simple Greetings"}
event: error             data: {"code": "STREAM_ERROR", "message": "The response failed."}
```

Tokens are the provider's own chunks, not a split of a finished reply. Closing
the connection closes the graph stream and releases the conversation lock.

### HITL approvals

When a sensitive tool is proposed, the turn stops and `chat` reports
`"status": "awaiting_approval"` with an `approval_id`, or the stream emits
`approval_required`. Nothing executes until a decision arrives.

```bash
# 1. What is waiting
curl -s http://127.0.0.1:8000/api/v1/approvals -H "authorization: Bearer $TOKEN"
# 2. Decide
curl -s -X POST http://127.0.0.1:8000/api/v1/approvals/$APPROVAL_ID/decision \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"decision":"edit","edited_arguments":{"selling_price":95000}}'
```

Decisions are `approve`, `edit` (requires `edited_arguments`), and `reject`
(optional `comment`). `respond` returns **422**: the graph has no such branch, and
silently treating free text as a rejection would misreport the human's intent.

The `approval_id` is an HMAC over the caller, the thread, the live interrupt id,
and the graph's own approval token. It is not stored, and the internal token is
never returned. A decision is accepted only if that handle still matches the
_currently pending_ interrupt, re-checked under the conversation lock, so a stale,
forged, or replayed decision cannot execute a tool. A second decision is `409`.

### Documents

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/documents \
  -H "authorization: Bearer $TOKEN" -F 'file=@docs/handbook.md'
```

Uploads are size-limited while being received (413), verified by content rather
than extension (415), stored under server-generated names, and indexed into the
caller's own namespace. Identical bytes are skipped rather than duplicated.
Responses never contain the storage path, and `search_documents` used by the agent
is scoped to the authenticated user, so retrieval cannot surface another user's
documents.

### Notes and limitations

- **One worker — on either backend.** With Postgres the _database_ can serve
  multiple processes, but the rest of the process is still per-instance: the
  BM25 corpus is built in memory, and the inventory JSON is a single writer. Run
  one `uvicorn` worker per container and scale there only after moving those into
  the database.
- `GET /api/v1/approvals` reads state once per thread (O(threads)).
- API keys are operator identities, not a user-management system: no refresh
  tokens, no rate limiting, no HTTPS termination. Terminate TLS in front of it
  (ALB, CloudFront, or nginx) and keep the service on a private network.
- Set `API_ENV=production` in a deployment: that disables `/docs`, `/redoc`, and
  `/openapi.json`, and refuses to start with a placeholder `JWT_SECRET_KEY`.
- On Windows, `uvicorn[standard]`'s `httptools`/`uvloop` wheels have crashed
  (`0xC0000005`); pass `http="h11"` if that happens.

See `FASTAPI-SPRINTS.md` for how the work was sequenced and what was verified.

## Deploying

Two processes, one database.

```
browser ──HTTPS──▶ CDN / ALB ──▶ Next.js (BFF)  ──HTTP──▶ FastAPI ──▶ PostgreSQL + pgvector
```

The browser never talks to FastAPI directly: every call goes through the Next.js
BFF (`/api/backend/*`), which attaches the bearer token from an HttpOnly cookie.
That is what keeps the JWT out of client JavaScript.

**Required for a real deployment:**

| Setting                      | Why                                                                                 |
| ---------------------------- | ----------------------------------------------------------------------------------- |
| `API_ENV=production`         | disables `/docs`, `/redoc`, `/openapi.json`; refuses a placeholder JWT secret       |
| `JWT_SECRET_KEY`             | a real random value — `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `API_KEYS`                   | operator identities, e.g. `alice=<long-random-string>`                              |
| `POSTGRES_DSN`               | point at RDS/Cloud SQL, not localhost                                               |
| `CORS_ORIGINS`               | the exact web origin; never `*` with credentials enabled                            |
| `SESSION_COOKIE_SECURE=true` | so the session cookie is only sent over HTTPS                                       |
| `OPENAI_API_KEY`             | chat and embeddings                                                                 |

**Checklist:**

1. Managed PostgreSQL with the `vector` extension available. On RDS this is
   supported; enable it and run `CREATE EXTENSION IF NOT EXISTS vector;` once.
2. Run the API and the web app as separate services. Each container runs **one**
   uvicorn worker (see the limitations above).
3. Terminate TLS at the edge and set `x-forwarded-proto: https`, so the API
   emits HSTS and the cookie is marked `Secure`.
4. Health checks: `/health` (liveness) and `/health/ready` (readiness — verifies
   the database, graph, vector store, and configuration).
5. Do not bake `.env` into an image; inject secrets from the platform's secret
   manager.

The frontend already sets a CSP, `X-Frame-Options`, `X-Content-Type-Options`,
`Referrer-Policy`, and `Permissions-Policy`, and removes `X-Powered-By`.

> **Deploying to AWS?** The concrete, costed, sprint-by-sprint plan for a
> single-EC2 deployment (Docker Hub + GitHub Actions + Caddy + SSM, no ALB or
> NAT) lives in [aws-deployment-ci-cd-plan.md](./aws-deployment-ci-cd-plan.md).
> The operational runbook that plan produces is [AWS-DEPLOYMENT.md](./AWS-DEPLOYMENT.md).

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

  ● MODEL    gpt-4o-mini       ● STORAGE  connected
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

| Marker                               | Row                                                           |
| ------------------------------------ | ------------------------------------------------------------- |
| `YOU`                                | your message                                                  |
| `BAYAZID AI`                         | the assistant's reply, streamed live or rendered as Markdown  |
| `● Executing tool: <name> · running` | a tool call, announced when it starts                         |
| `✓ Completed · 0.3s`                 | a tool result, with measured elapsed time                     |
| `✗ Failed`                           | a failed tool or error, printed inline so it stays selectable |

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

| Shortcut      | Action                                 |
| ------------- | -------------------------------------- |
| `Tab`         | Accept the selected completion         |
| `Up` / `Down` | Navigate suggestions and input history |
| `Enter`       | Submit input                           |
| `Ctrl+C`      | Interrupt input and continue chatting  |
| `Ctrl+D`      | Exit on an empty line                  |

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

| Command         | Description                                  | Category     |
| --------------- | -------------------------------------------- | ------------ |
| `/help`         | Show commands, or details for one command    | General      |
| `/clear`        | Clear the terminal screen                    | General      |
| `/status`       | Show model, database, graph, and tracing     | General      |
| `/ingest`       | Index Markdown, text, and PDF files          | General      |
| `/documents`    | List indexed documents and namespaces        | General      |
| `/version`      | Show the application version                 | General      |
| `/exit`         | Exit the chatbot                             | General      |
| `/new`          | Create a new conversation                    | Conversation |
| `/threads`      | Open the session picker to switch            | Conversation |
| `/history`      | Show the current conversation history        | Conversation |
| `/approvals`    | Show approvals waiting for this conversation | Conversation |
| `/rename`       | Rename the current conversation              | Conversation |
| `/delete`       | Delete a conversation and its checkpoints    | Conversation |
| _anything else_ | Send a chat message                          | —            |

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
`get_tools(notes_repository, document_service, inventory_service)`. When it emits
tool calls, LangGraph's `ToolNode` executes read-only tools and routes back to the
chat node. Calls whose tool name is in `SENSITIVE_TOOLS` go to the approval node
instead, which pauses the graph until a human decides. Tool activity is printed as
it happens:

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

### Registered tools (91)

| Category           | Module             | Tools                                                                                                                                                                                                                                                                                 |
| ------------------ | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Core               | `builtin.py`       | `calculator`, `get_current_time`                                                                                                                                                                                                                                                      |
| Local utilities    | `utilities.py`     | `convert_units`, `generate_uuid`, `generate_password`, `hash_text`, `base64_encode`, `base64_decode`, `format_json`, `regex_search`, `summarize_text`                                                                                                                                 |
| Everyday life      | `life.py`          | `calculate_loan_payment`, `calculate_tip_split`, `calculate_bmi`, `calculate_age`, `days_between`, `convert_timezone`, `estimate_fuel_cost`                                                                                                                                           |
| Notes (per thread) | `notes.py`         | `save_note`, `list_notes`, `search_notes`, `delete_note` — scoped to the active conversation                                                                                                                                                                                          |
| Retrieval (RAG)    | `documents.py`     | `search_documents`, `list_documents` — hybrid search (pgvector + BM25 fused with RRF) over ingested text and PDFs, searched per namespace                                                                                                                                                |
| Inventory / ERP    | `inventory/tools/` | 54 tools for products, categories, stock, movements, customers, suppliers, sales, invoices, payments, purchase orders, accounts, expenses, returns, and approvals. 15 are HITL-protected.                                                                                             |
| Mock API services  | `mocks.py`         | `fetch_url`, `get_news`, `get_weather`, `get_stock_price`, `convert_currency`, `send_email`, `send_slack_message`, `create_calendar_event`, `list_calendar_events`, `translate_text`, `find_recipe`, `get_holidays`, `track_package` (`web_search` is defined but currently disabled) |

All tools that need an external service (`mocks.py`) return simulated data and
include `"mock": true` in their JSON. They make **no network calls** and need no
keys. Calendar events are stored in memory for the life of the process, while
notes are persisted in PostgreSQL (the `notes` table) and scoped to the
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

## Inventory & ERP Demo (HITL)

The agent now understands a fictional Bangladeshi electronics and office-supply
distributor. The dataset contains 10 categories, 36 products, 9 suppliers, 18
customers, 10 employees, 3 warehouses, stock and movements, 18 sales, 13 invoices,
payments, 9 purchase orders, 14 accounts, expenses, journal entries, sales
targets, returns, approvals, and an audit log. Currency is BDT, dates are
`YYYY-MM-DD`, and the timezone is `Asia/Dhaka`. All data is fictional. See
[`inventory-data/README.md`](./inventory-data/README.md) for the entity map and
counts.

### Read-only questions

These answer directly, without an approval panel:

```text
How many Latitude Business Laptops are available?
Which products are running low?
Show all unpaid invoices.
How much does customer CUS-004 owe?
What is our financial position?
Show stock movements for PRD-1001.
```

The model maps those to `check_product_availability`, `check_low_stock`,
`get_outstanding_invoices`, `get_customer_balance`, `get_financial_summary`, and
`get_stock_movements`.

### Sensitive operations

Fifteen tools change business state and pause for approval:
`update_product`, `deactivate_product`, `update_customer`, `adjust_stock`,
`transfer_stock`, `create_sale`, `update_sale`, `cancel_sale`, `create_invoice`,
`record_payment`, `create_purchase_order`, `update_purchase_order`,
`receive_purchase_order`, `create_expense`, and `process_return`.

```text
YOU
Increase the selling price of PRD-1001 to 95000.

BAYAZID AI
  ● Executing tool: update_product  ● running
╭────────────────────── HUMAN APPROVAL REQUIRED ───────────────────────╮
│ Action: Update Product                                               │
│                                                                      │
│ Product: Latitude Business Laptop 14                                 │
│ SKU: LAP-BIZ-14-001                                                  │
│ Current Selling Price: BDT 89,500                                    │
│ Proposed Selling Price: BDT 95,000                                   │
│                                                                      │
│ Requested By: AI Agent                                               │
│ Reason: The agent requested a sensitive inventory operation.         │
│ Reviewer: Shirin Sultana (EMP-006)                                   │
│                                                                      │
│ [A] Approve    [E] Edit Arguments    [R] Reject                      │
╰──────────────────────────────────────────────────────────────────────╯
Decision [A]pprove / [E]dit / [R]eject:
```

- **A** executes the proposal with the original arguments.
- **E** opens a field-by-field editor. It lists every schema field with its
  current value, accepts a field number or name, coerces the new value to the
  declared type, shows only the changed values, and asks for confirmation.
- **R** executes nothing and returns a rejection to the model.

```text
Editable arguments
  1. product_id = 'PRD-1001'
  2. name = 'Latitude Business Laptop 14 Pro'
  ...
Field to edit (number/name, 'c' to cancel, blank to finish): 2
name [Latitude Business Laptop 14 Pro]: Latitude Business Laptop 14 Supreme
...
Proposed argument changes
  name: 'Latitude Business Laptop 14 Pro' -> 'Latitude Business Laptop 14 Supreme'
Execute with these arguments? (y/n):
```

Every approval prompt terminates its own line. A decision prints
`Approval recorded. Continuing…`; a cancel prints `Returning to chat. Use
/approvals to inspect pending actions.` In both cases the main framed prompt is
restored, so the approval screen cannot trap the session. Approval questions use
a plain console prompt rather than the framed composer, which keeps the main
`PromptSession` untouched; `/approve`, `/edit`, and `/reject` are accepted as well
as `A`, `E`, and `R`. `/approvals` is a read-only command that lists the live
interrupt for the current thread and the seeded pending business approvals.

The panel is followed by the real tool result and the model's final answer. A
rejected operation is never claimed as successful, and an edited argument is
reported from the tool result rather than the model's original proposal. Pending
approvals are stored in the existing `SqliteSaver` checkpoint, so quitting and
restarting offers the same panel for the restored thread. Repeating a resume
cannot duplicate a financial or inventory effect: each sensitive call carries an
`operation_id` recorded in the same atomic JSON write as the mutation.

### What each workflow enforces

- **Delete product** — soft delete only; historical sales, POs, and movements keep
  their references.
- **Price or title update** — the panel shows current and proposed values; field
  edits execute after confirmation and are audited.
- **Stock adjustment** — a reason is required; on-hand and available quantity can
  never go negative.
- **Discount approval** — `update_sale` previews the current discount and projected
  total; the edited discount is recalculated with the same tax formula.
- **Purchase order** — created as `pending_approval`; only approved orders can be
  ordered and received into stock.
- **Payment** — must be positive and cannot exceed the invoice balance; invoice,
  customer balance, and sale status update together.
- **Return** — quantity is bounded by the unreturned amount; approval restocks the
  warehouse, writes a `sales_return` movement, and records the refund.

Reset the demo dataset after experimenting:

```bash
cp inventory-data/inventory/inventory_data.seed.json \
   inventory-data/inventory/inventory_data.json
```

Read [`HITL.md`](./HITL.md) for the interrupt/resume architecture,
decision types, idempotency details, and testing scenarios.

## Knowledge Base (RAG)

Supported files: `.md`, `.markdown`, `.txt`, `.rst`, and `.pdf`. Drop them in
`docs/` (or any folder) and index them:

```text
/ingest docs handbook          # index docs/ into the "handbook" namespace
/documents                     # list namespaces and indexed files
/ingest docs policies --force  # re-embed and rebuild the indexes
```

Each namespace's embeddings live in the `document_chunks` rows themselves (a
`pgvector` column with an HNSW index). Text files use one section; PDFs are split
per page so results cite a page number. Unchanged files are skipped by content
hash; `--force` overrides that. `search_documents` is exposed to the model, which
calls it for questions about the ingested material and cites title/source/page.

### How hybrid search works

Retrieval runs two independent searches for the same query and fuses them:

1. **Vector search (pgvector)** — the query is embedded with
   `text-embedding-3-small`, L2-normalized, and compared against the namespace's
   `embedding_vec` column, using the HNSW index when pgvector is installed (and a
   plain array scan otherwise). Scores are cosine similarity, so this finds chunks
   that are _semantically_ related even with different wording.
2. **BM25 keyword search** — chunk text from `document_chunks` is tokenized
   (lowercase alphanumeric terms) into an in-memory `BM25Okapi` index per
   namespace. This finds _exact_ terms: names, employee IDs (`EMP-1042`), product
   codes (`SKU-9931`), and technical jargon that embeddings can blur.
3. **Reciprocal Rank Fusion (RRF)** — both result lists are combined by rank
   position, not by score, so cosine similarity and BM25 scores never have to be
   normalized against each other:

    ```text
    RRF(d) = sum over each list of 1 / (k + rank(d))
    ```

    With `k = 60`, a chunk ranked first in one list scores `1/61 ≈ 0.0164`; a
    chunk appearing in both lists accumulates both contributions and rises to the
    top. Results are deduplicated by `document_chunks.row_id`, so the same chunk
    found by both retrievers appears once with a boosted score. The final Top-K is
    returned, best first.

PostgreSQL remains the source of truth, for the vectors and for the text. BM25
needs no extra database and no persistence: indexes are built from
`document_chunks` on first use and rebuilt whenever a namespace's chunk set
changes (detected with a cheap count/max/sum `row_id` fingerprint), so ingestion,
re-ingestion, and deletion can never leave a stale keyword index. After a restart
the first search rebuilds from PostgreSQL.

Both searches run concurrently on a two-worker thread pool (the retrievers are
blocking and thread-safe), which keeps the synchronous service synchronous. If
one retriever fails, the other still contributes; only a total failure both is
reported as a retrieval error.

### Configuring retrieval

| Variable                | Default  | Meaning                                                   |
| ----------------------- | -------- | --------------------------------------------------------- |
| `RAG_SEARCH_MODE`       | `hybrid` | `hybrid`, `vector`, or `bm25`                             |
| `RAG_VECTOR_CANDIDATES` | `10`     | chunks requested from the vector search                   |
| `RAG_BM25_CANDIDATES`   | `10`     | chunks requested from BM25                                |
| `RAG_TOP_K`             | `4`      | final fused result count (`k` tool argument overrides it) |
| `RAG_RRF_K`             | `60`     | RRF rank-damping constant                                 |
| `RAG_MIN_SCORE`         | `0.15`   | cosine floor, applied in `vector` mode only               |

`RAG_SEARCH_MODE=vector` restores the previous cosine-only behaviour exactly,
and `bm25` runs keyword search with no embedding call. The service also exposes
`search_vector()`, `search_bm25()`, and `search_hybrid()` directly so the modes
can be compared without changing configuration.

Notes:

- RRF scores are not cosine similarities. In `hybrid` mode `RAG_MIN_SCORE` is not
  applied, because RRF scores are tiny by construction; each hit still reports its
  `vector_score` and `bm25_score` so the contribution of each retriever is
  visible.
- Scanned/image-only PDFs have no text layer and are reported as ingest errors —
  there is no OCR.
- A search `namespace` must be a value from `/documents` (the ingest namespace),
  not a document title. An unknown namespace returns an error listing the valid
  ones; omitting it searches everything.
- Changing `EMBEDDINGS_MODEL` or `EMBEDDING_DIMENSIONS` invalidates existing
  embeddings: the stored dimension is fixed in `rag_meta`, and the schema refuses
  to start when the configured size disagrees. Re-ingest with `--force` against a
  freshly initialised database. The BM25 index needs no rebuild step — it is
  derived from PostgreSQL on demand.

## Streaming

`ChatService.stream_turn()` yields transport-neutral events:

- `TurnEvent(type="token", content="...")` for each streamed chunk.
- `TurnEvent(type="tool_call", name=..., content="...")` when the model requests
  a tool; `content` holds the JSON arguments.
- `TurnEvent(type="tool_result", name=..., content="...")` when that tool
  returns; `content` holds the result.
- `TurnEvent(type="interrupt", name="approval", payload=...)` when the graph
  pauses for a sensitive operation and needs a human decision.
- `TurnEvent(type="done", title=...)` when the turn is persisted; `title` is set
  only when a new title was generated on the first turn.

`ChatService.resume_turn(thread_id, decision)` streams the continuation after an
approval, using `Command(resume=decision)` on the same thread. The CLI prints
these events directly (`● Executing tool: …` / `✓ Completed` lines for tool
activity, an approval panel for `interrupt`). A future SSE endpoint can map the
same events to `event: token` / `event: tool_call` / `event: tool_result` /
`event: interrupt` / `event: done` without changing the service.

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

## Persistence

One PostgreSQL database holds four independent concerns. `postgres_schema.py`
owns the DDL, and the repositories are written once against `sql_backend.py`.

1. **Thread metadata** — the `threads` table (`thread_id`, `title`, `owner_id`,
   `created_at`, `updated_at`), managed by `ThreadRepository`.
2. **Notes** — the `notes` table (`note_id`, `thread_id`, `title`, `content`,
   `created_at`), managed by `NotesRepository`. Notes survive restarts and are
   private to the conversation that created them.
3. **Knowledge base** — `documents` and `document_chunks` hold document text and
   metadata; `rag_meta` records the embedding dimension. The embedding lives in
   `document_chunks.embedding_vec` (`vector(1536)`) with an HNSW index. The BM25
   index is in memory only and derived from `document_chunks`, so the database
   remains the single source of truth for chunk text.
4. **Conversation state** — LangGraph checkpoint tables, created and managed by
   `PostgresSaver.setup()`. Pending HITL approvals live here too, which is why
   they survive a restart.

All four share one connection, so they also share one lock: psycopg connections
run one command at a time. The container hands that lock to the checkpointer and
has it commit after each write, because the connection is not autocommit and
psycopg rolls back on close.

The inventory dataset is deliberately **not** in the database. It is one JSON
document (`INVENTORY_DATA_PATH`) with atomic writes, whole-dataset validation, and
a process lock. This keeps the ERP exercise inspectable and easy to reset without
introducing a schema or ORM. See `inventory-data/README.md`.

Deleting a thread removes its checkpoints first, then its metadata. Deleting a
thread while it is active creates a replacement conversation. Notes and
documents are kept until explicitly deleted, and notes are only visible from
their own thread. Deleting a thread does not delete its notes or documents.

Back up the database: it holds the documents, their embeddings, and the
conversation checkpoints. There is no separate index directory to keep in sync.

## Running Tests

```bash
uv run pytest
```

The suite runs against a real PostgreSQL server (see [Tests](#tests)) with fake
graph/LLM implementations, so it never calls the OpenAI API. It covers
configuration precedence, container wiring and schema creation, thread lifecycle
and ordering, checkpoint cleanup on delete, streaming and title generation, tool
execution and event emission, the individual tool implementations (calculators,
utilities, notes, documents, and mocks), notes persistence across connections,
document ingestion (text and PDF), pgvector indexing and retrieval, CLI rendering,
the interactive command loop, and package entry points.

The CLI has dedicated coverage across these test files:

| Test file                        | Covers                                                          |
| -------------------------------- | --------------------------------------------------------------- |
| `test_cli_registry.py`           | command lookup, normalization, grouping, prefix and fuzzy match |
| `test_cli_commands.py`           | the command table, dispatch routing, and every handler          |
| `test_cli_chat.py`               | streaming, tool visibility, Markdown detection, error display   |
| `test_cli_input.py`              | completion logic, glyph fallback, loop behavior, input routing  |
| `test_cli_prompt_integration.py` | real `PromptSession` Tab completion for commands and arguments  |
| `test_cli_banner.py`             | emerald theme, the framed welcome hero, and the status readout  |
| `test_cli_rendering.py`          | background grid, framed input, and timed tool feedback          |
| `test_cli_picker.py`             | session picker: timing, filtering, selection, keyboard drive    |

RAG-specific tests:

| Test file                      | Covers                                                           |
| ------------------------------ | ---------------------------------------------------------------- |
| `test_loaders.py`              | text normalization, PDF pages/encryption/scanned/truncation      |
| `test_pg_vector_store.py`      | pgvector usage, cosine scores, namespace filtering, owner isolation |
| `test_bm25_store.py`           | keyword/ID matching, namespaces, rebuild and deletion freshness  |
| `test_rrf.py`                  | RRF formula, dedup, tie ordering, empty lists, Top-K limiting    |
| `test_hybrid_search.py`        | concurrent retrieval, fusion, fallback, lifecycle, metadata      |
| `test_documents_repository.py` | document/chunk SQL, page round-trip, delete, schema guards       |
| `test_document_service.py`     | ingest, dedupe, `force`, limits, compensation on index failure   |
| `test_document_tools.py`       | tool JSON shapes and error strings                               |
| `test_repository_contract.py`  | the repository contract: timestamps, ids, owner scoping          |
| `test_api_isolation.py`        | owner filtering before fusion, across all three search modes     |

Run just the hybrid-search tests:

```bash
uv run pytest tests/test_rrf.py tests/test_bm25_store.py tests/test_hybrid_search.py -v
```

Inventory and HITL tests:

| Test file                   | Covers                                                                                                                         |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `test_inventory_dataset.py` | dataset validity, FKs, financial/inventory consistency, atomic rollback, concurrent transactions                               |
| `test_inventory_service.py` | catalogue, stock, sales, invoices, payments, POs, returns, idempotency, operator mapping, log retention                        |
| `test_inventory_tools.py`   | 54 tools, sensitive/read-only split, descriptions, previews                                                                    |
| `test_hitl.py`              | interrupt, approve/edit/reject, stale token, multiple approvals, discount and stock workflows, restart, no duplicate execution |
| `test_cli_approval.py`      | approval panel, field-level editing and type coercion, invalid values, edit cancellation, startup resume                       |
| `test_cli_commands.py`      | `/approvals` live-interrupt and seeded-approval rendering                                                                      |

```bash
uv run pytest tests/test_inventory_dataset.py tests/test_inventory_service.py \
  tests/test_inventory_tools.py tests/test_hitl.py tests/test_cli_approval.py -v
```

The inventory fixtures copy the dataset into `tmp_path`, so tests never mutate the
checked-in working file. HITL restart tests use a real `PostgresSaver` in the
test's own schema, and commit explicitly — which is what the container's
checkpointer does on their behalf.

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
- [x] PostgreSQL database integration
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
- [x] Retrieval-augmented generation (pgvector, one index per namespace)
- [x] Hybrid search: BM25 + HNSW fused with Reciprocal Rank Fusion
- [x] PDF ingestion with page-level citations
- [x] ERP-style inventory domain over an interconnected JSON dataset
- [x] Dataset validation, atomic writes, and idempotent business operations
- [x] Human-in-the-Loop approvals with LangGraph interrupts and resume
- [x] CLI approve / edit-arguments / reject workflow
- [x] Pending approval persistence across restarts and audit logging
- [x] Read-only `/approvals` command
- [x] Field-level approval editing with type coercion
- [x] Reviewer identity mapped to an employee in audit records
- [x] Configurable retention caps for operation and audit logs
- [x] FastAPI backend integration
- [x] Agentic decision-making
- [x] Cross-thread memory management
- [x] Advanced agentic workflows
- [x] Frontend integration
- [ ] AWS deployment
