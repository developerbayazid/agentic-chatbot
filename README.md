# Agentic AI Chatbot

A hands-on project for learning and building an **Agentic AI Chatbot** with Python,
LangChain, and LangGraph.

The application is currently a modular, interactive **CLI**. It preserves
thread-isolated conversations in SQLite through LangGraph's `SqliteSaver`,
generates conversation titles automatically, streams model responses token by
token, and supports tool calling through a LangGraph tool loop. Optional
LangSmith tracing sends runs to LangSmith for debugging and monitoring. The code
is split into presentation, service, graph, and persistence layers so a FastAPI
backend can be added later without rewriting business logic.

For the full design and migration plan, see [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Project Goals

- Build an AI-powered conversational chatbot.
- Understand the fundamentals of Agentic AI.
- Explore LangChain and LangGraph through practical implementation.
- Preserve conversation history and thread isolation with SQLite.
- Keep business logic framework-agnostic so it is reusable by a CLI or an API.
- Provide a tool-calling loop with a single registry of local and mock-backed tools.
- Add a FastAPI backend and frontend later without restructuring the core.

## Tech Stack

| Technology                        | Purpose                                  |
| --------------------------------- | ---------------------------------------- |
| **Python**                        | Primary language                         |
| **LangChain**                     | LLM application development              |
| **LangGraph**                     | Graph-based workflow orchestration       |
| **LangGraph SQLite Checkpointer** | Conversation state persistence           |
| **LangSmith**                     | Tracing and observability                |
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
│       ├── config.py            # settings + LangSmith env export
│       ├── llm.py               # ChatOpenAI factory
│       ├── database.py          # SQLite connection + schema
│       ├── models.py            # Thread and TurnEvent dataclasses
│       ├── repository.py        # ThreadRepository (thread-table SQL)
│       ├── graph/
│       │   ├── state.py         # ChatState
│       │   ├── nodes.py         # chat node
│       │   └── workflow.py      # compiled LangGraph (chat ⇄ tools)
│       ├── services/
│       │   ├── chat_service.py   # streaming turns + history
│       │   ├── thread_service.py # thread lifecycle
│       │   └── title_service.py  # automatic titles
│       └── tools/
│           ├── builtin.py        # calculator, get_current_time
│           ├── utilities.py      # local helpers (hash, base64, units, ...)
│           ├── life.py           # loan, tip, BMI, age, timezone, fuel
│           ├── notes.py          # in-memory note taking
│           ├── mocks.py          # mocked API tools (weather, search, ...)
│           └── registry.py       # ALL_TOOLS / get_tools()
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
- **Graph** (`graph/`) — LangGraph state, the chat node, the `ToolNode`, and the
  compiled chatbot.
- **Tools** (`tools/`) — `@tool` implementations registered in `registry.py` and
  executed by LangGraph's `ToolNode`.
- **Persistence** (`repository.py`, `database.py`) — thread metadata SQL.
- **Checkpointer** — `SqliteSaver` stores conversation messages and graph state.
- **Container** (`container.py`) — builds and owns the SQLite connection,
  checkpointer, LLM, tool-bound LLM, compiled graph, and services.

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

## Tools

The tool-bound LLM receives every schema in `ALL_TOOLS`. When it emits tool
calls, LangGraph's `ToolNode` executes them and routes back to the chat node for
a final answer. Tool activity is printed as it happens:

```text
Assistant:
[tool] get_weather({"location": "Dhaka", "unit": "celsius"})
[tool result: get_weather] {"temperature": 27, ...}
It is currently 27°C in Dhaka.
```

### Registered tools (36)

| Category            | Module         | Tools                                                                                                                                                                                                 |
| ------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Core                | `builtin.py`   | `calculator`, `get_current_time`                                                                                                                                                                      |
| Local utilities     | `utilities.py` | `convert_units`, `generate_uuid`, `generate_password`, `hash_text`, `base64_encode`, `base64_decode`, `format_json`, `regex_search`, `summarize_text`                                                 |
| Everyday life       | `life.py`      | `calculate_loan_payment`, `calculate_tip_split`, `calculate_bmi`, `calculate_age`, `days_between`, `convert_timezone`, `estimate_fuel_cost`                                                            |
| Notes               | `notes.py`     | `save_note`, `list_notes`, `search_notes`, `delete_note`                                                                                                                                              |
| Mock API services   | `mocks.py`     | `web_search`, `fetch_url`, `get_news`, `get_weather`, `get_stock_price`, `convert_currency`, `send_email`, `send_slack_message`, `create_calendar_event`, `list_calendar_events`, `translate_text`, `find_recipe`, `get_holidays`, `track_package` |

All tools that need an external service (`mocks.py`) return simulated data and
include `"mock": true` in their JSON. They make **no network calls** and need no
keys. Calendar events and notes are stored in memory for the life of the process.
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

Then append `word_count` to `ALL_TOOLS` in
`src/agentic_chatbot/tools/registry.py`. `create_llm` and `ToolNode` pick it up
automatically; no graph, service, or CLI changes are needed.

### Example prompts

- "What's the monthly payment on a $250,000 mortgage at 6.5% for 30 years?"
- "Split a $120 dinner bill with an 18% tip across 4 people."
- "My weight is 70 kg and I'm 1.75 m tall — what's my BMI?"
- "What time is 12:00 UTC in Asia/Dhaka?"
- "How many business days between 2026-11-01 and 2026-12-15?"
- "Save a note titled 'Grocery list' with milk, eggs, and spinach."
- "Search my notes for 'spinach'."
- "What's the weather in Dhaka?" / "Find a recipe for chicken curry."
- "What are the public holidays in Bangladesh in 2027?"
- "Track my package AB123456789."
- "Convert 250 USD to BDT."
- "Create a calendar event 'Design review' on 2026-12-01 at 10:00 for 45 minutes."
- "Search the web for LangGraph tool calling best practices."

## Streaming

`ChatService.stream_turn()` yields transport-neutral events:

- `TurnEvent(type="token", content="...")` for each streamed chunk.
- `TurnEvent(type="tool_call", name=..., content="...")` when the model requests
  a tool; `content` holds the JSON arguments.
- `TurnEvent(type="tool_result", name=..., content="...")` when that tool
  returns; `content` holds the result.
- `TurnEvent(type="done", title=...)` when the turn is persisted; `title` is set
  only when a new title was generated on the first turn.

The CLI prints these events directly (`[tool]` / `[tool result: ...]` lines for
tool activity). A future SSE endpoint can map the same events to `event: token` /
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
delete, streaming and title generation, tool execution and event emission, the
individual tool implementations (calculators, utilities, notes, and mocks), CLI
rendering, the interactive command loop, and package entry points.

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
- [ ] FastAPI backend integration
- [ ] Agentic decision-making
- [ ] Cross-thread memory management
- [ ] Advanced agentic workflows
- [ ] Frontend integration

## Current Status

The modular CLI is operational. Conversation threads, automatic titles, history,
streaming, tool calling, and SQLite persistence all run through the service layer
under `src/agentic_chatbot/`. Thirty-six tools are registered in
`src/agentic_chatbot/tools/` — local utilities plus mock implementations of
common API-backed tools (weather, search, email, calendar, currency, …) that
return `"mock": true` data until real credentials are configured. Add a tool to
`registry.py` to expose it to the model. LangSmith tracing is available when
enabled through `.env`. FastAPI is not part of the current runtime; it is the
next planned milestone, and `ARCHITECTURE.md` documents how to wire it in
without touching the services.
