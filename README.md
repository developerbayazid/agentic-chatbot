# Agentic AI Chatbot

A hands-on project for learning and building an **Agentic AI Chatbot** with Python,
LangChain, and LangGraph.

The application is currently a modular, interactive **CLI**. It preserves
thread-isolated conversations in SQLite through LangGraph's `SqliteSaver`,
generates conversation titles automatically, and streams model responses token by
token. The code is split into presentation, service, graph, and persistence layers
so a FastAPI backend can be added later without rewriting business logic.

For the full design and migration plan, see [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Project Goals

- Build an AI-powered conversational chatbot.
- Understand the fundamentals of Agentic AI.
- Explore LangChain and LangGraph through practical implementation.
- Preserve conversation history and thread isolation with SQLite.
- Keep business logic framework-agnostic so it is reusable by a CLI or an API.
- Prepare the architecture for tool calling, conditional routing, and agent nodes.
- Add a FastAPI backend and frontend later without restructuring the core.

## Tech Stack

| Technology                        | Purpose                                  |
| --------------------------------- | ---------------------------------------- |
| **Python**                        | Primary language                         |
| **LangChain**                     | LLM application development              |
| **LangGraph**                     | Graph-based workflow orchestration       |
| **LangGraph SQLite Checkpointer** | Conversation state persistence           |
| **OpenAI**                        | Large language models                    |
| **Pydantic / pydantic-settings**  | Configuration loading and validation     |
| **SQLite**                        | Thread metadata and checkpoint storage   |
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
│
├── src/
│   └── agentic_chatbot/
│       ├── __init__.py          # Exposes main() for the console script
│       ├── __main__.py          # python -m agentic_chatbot entry point
│       ├── cli.py               # Terminal UI and command loop
│       ├── container.py         # Composition root (wires all resources)
│       ├── config.py            # pydantic-settings configuration
│       ├── llm.py               # ChatOpenAI factory
│       ├── database.py          # SQLite connection + schema
│       ├── models.py            # Thread and TurnEvent dataclasses
│       ├── repository.py        # ThreadRepository (thread-table SQL)
│       ├── graph/
│       │   ├── state.py         # ChatState
│       │   ├── nodes.py         # chat node
│       │   └── workflow.py      # compiled LangGraph
│       └── services/
│           ├── chat_service.py   # streaming turns + history
│           ├── thread_service.py # thread lifecycle
│           └── title_service.py  # automatic titles
│
├── tests/                       # Pytest suite (fakes + temporary SQLite)
├── notebooks/                   # Learning notebooks
└── data/                        # Optional alternate database location
```

## Architecture Summary

The application follows a one-way dependency flow:

```text
cli.py  →  container.py  →  services  →  graph / repository  →  SQLite
```

- **Presentation** (`cli.py`) — reads input and prints output only.
- **Services** (`services/`) — chat orchestration, thread lifecycle, titles.
  Independent of any UI or HTTP framework.
- **Graph** (`graph/`) — LangGraph state, nodes, and the compiled chatbot.
- **Persistence** (`repository.py`, `database.py`) — thread metadata SQL.
- **Checkpointer** — `SqliteSaver` stores conversation messages and graph state.
- **Container** (`container.py`) — builds and owns the SQLite connection,
  checkpointer, LLM, compiled graph, and services.

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

Notes:

- `DATABASE_PATH` defaults to `chatbot_memory.db` in the current directory.
- An existing `chatbot_memory.db` is reused as-is; the schema matches previous
  versions of the project.
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

## CLI Commands

| Command         | Description                               |
| --------------- | ----------------------------------------- |
| `/new`          | Create a new conversation                 |
| `/threads`      | List all conversations                    |
| `/switch`       | Switch to another conversation by ID      |
| `/history`      | Show the current conversation history     |
| `/rename`       | Rename the current conversation           |
| `/delete`       | Delete a conversation and its checkpoints |
| `/help`         | Show available commands                   |
| `/exit`         | Exit the chatbot                          |
| _anything else_ | Send a chat message                       |

## Streaming

`ChatService.stream_turn()` yields transport-neutral events:

- `TurnEvent(type="token", content="...")` for each streamed chunk.
- `TurnEvent(type="done", title=...)` when the turn is persisted; `title` is set
  only when a new title was generated on the first turn.

The CLI prints these events directly. A future SSE endpoint can map the same
events to `event: token` / `event: done` without changing the service.

## SQLite Persistence

One SQLite database holds two independent concerns:

1. **Thread metadata** — the `threads` table (`thread_id`, `title`,
   `created_at`, `updated_at`), managed by `ThreadRepository`.
2. **Conversation state** — LangGraph checkpoint tables created and managed by
   `SqliteSaver.setup()`.

Deleting a thread removes its checkpoints first, then its metadata. Deleting a
thread while it is active creates a replacement conversation.

## Running Tests

```bash
uv run pytest
```

The suite uses temporary SQLite databases and fake graph/LLM implementations, so
it never calls the OpenAI API. It covers configuration precedence, container
wiring and schema creation, thread lifecycle and ordering, checkpoint cleanup on
delete, streaming and title generation, CLI rendering, the interactive command
loop, and package entry points.

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
- [ ] FastAPI backend integration
- [ ] Tool calling and integration
- [ ] Agentic decision-making
- [ ] Cross-thread memory management
- [ ] Advanced agentic workflows
- [ ] Frontend integration

## Current Status

The modular CLI is operational. Conversation threads, automatic titles, history,
streaming, and SQLite persistence all run through the service layer under
`src/agentic_chatbot/`. FastAPI is not part of the current runtime; it is the next
planned milestone, and `ARCHITECTURE.md` documents how to wire it in without
touching the services.
