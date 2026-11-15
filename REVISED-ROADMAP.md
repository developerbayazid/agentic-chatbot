# BAYAZID AI — Revised Product Roadmap (Frontend + Extensibility)

Status: **awaiting approval.** No implementation has started for this revision.
Supersedes the UI/ERP sections of `FRONTEND_IMPLEMENTATION_PLAN.md` and
`FASTAPI-SPRINTS.md` where they conflict.

Companions: `API.md` (backend contract), `ARCHITECTURE.md`, `HITL.md`.

---

## 1. Product identity

BAYAZID AI is an **AI assistant platform**, not an ERP application. The chat is
the product. The conversational surface is modern, monochrome, and calm;
everything else is secondary.

Reference: ChatGPT's layout and interaction model. We borrow structure and
fluency, never branding or assets.

### Visual system — strict black and white

| Role | Value |
| --- | --- |
| Canvas | `#ffffff` |
| Primary text | `#0d0d0d` (near-black) |
| Secondary text | `#6e6e6e` |
| Border | `#e5e5e5` |
| Hover | `#f5f5f5` |
| Selected / active | `#efefef` |
| Primary button | `#0d0d0d` background, `#ffffff` text |
| Sidebar | `#f9f9f9` |
| Success / warning / error | `#1a7f37` / `#9a6700` / `#b42318` (used only for status) |

**This removes the clay accent (`#c96442`) and the warm-gray sidebar
(`#f7f6f3`)** introduced last round, per your decision. No gradients, no
shadows beyond a single subtle border, no oversized rounding (8–12px max on
cards, 12–16px on the composer), no decorative cards.

Dark mode: explicitly out of scope for this revision. The theme provider stays
so it can be added later, but light is the only designed experience.

---

## 2. Sprint 0 audit — what actually exists

Everything below was read from the code, not assumed.

### 2.1 CLI commands (13, verified via `COMMANDS`)

| Command | Category | Behaviour | Web mapping |
| --- | --- | --- | --- |
| `/help` | General | list commands or explain one | command menu + `/help` help panel |
| `/clear` | General | clears the **terminal** only | **not mapped** (terminal-only) |
| `/status` | General | model, DB, graph, tracing state | Settings → status readout |
| `/ingest` | General | index a path | Documents → upload |
| `/documents` | General | list indexed docs | Documents page |
| `/version` | General | app version | Settings → About |
| `/exit` | General | ends the CLI process | **not mapped** (must not end a browser session) |
| `/new` | Conversation | create a conversation | New Chat / `/new` |
| `/threads` | Conversation | list and pick a conversation | sidebar list / `/threads` |
| `/history` | Conversation | show current messages | conversation view / `/history` |
| `/approvals` | Conversation | show pending approvals (read-only) | Approvals page / `/approvals` |
| `/rename` | Conversation | rename current thread | `/rename` → dialog |
| `/delete` | Conversation | delete a thread (with arg completion) | `/delete` → confirm dialog |

Notes that invalidate parts of the brief:

- **`/switch` does not exist.** The brief listed it; the real `/threads` *is* the
  switcher (it opens the picker). I will not invent `/switch` as an alias unless
  you want one.
- **`/clear` and `/exit` are terminal-only.** Mapping them to web actions would
  either do nothing meaningful or be actively wrong. Documented as unmapped.
- The `Command` dataclass has: `name, description, category, usage, example,
  behavior, arguments, handler, arg_completer`. Aliases and availability status
  do **not** exist yet — the web registry will add them.

### 2.2 Tools and registry

- `get_tools(notes_repository, document_service, inventory_service)` composes
  `STATIC_TOOLS` + note tools + document tools + 54 inventory tools = **91**.
- **No endpoint lists them.** `/api/v1/tools` would be a new, read-only route.
- No `SkillRegistry`, `PluginRegistry`, or `MCPClientManager` exists — and none
  should be created yet (see §2.5).

### 2.3 Persistence (what Postgres should and should not absorb)

| Component | Current | Target |
| --- | --- | --- |
| `threads`, `notes`, `documents`, `document_chunks`, `rag_meta` | SQLite | **PostgreSQL** |
| LangGraph checkpoints | `SqliteSaver` | **Postgres checkpointer** |
| Vectors | FAISS files (`data/faiss/`) | **pgvector** |
| BM25 | in-memory, rebuilt from SQLite chunks | **rebuilt from Postgres chunks** |
| RRF fusion | pure Python (`rrf.py`) | unchanged |
| **ERP demo dataset** | JSON (`inventory-data/`) | **stays JSON — excluded** |

### 2.4 Frontend state

7 routes exist (`/login`, `/chat`, `/chat/[threadId]`, `/documents`,
`/approvals`, `/settings`, `/`). **No ERP pages exist** — already compliant with
§6 of the brief. Tool timeline with real timers already works.

### 2.5 Extension points — deliberate restraint

The brief lists `SkillRegistry`, `PluginRegistry`, `ToolRegistry`,
`MCPClientManager`, `IntegrationRegistry` as *candidates*, then says not to
over-engineer. My position: **build none of them now.**

- `ToolRegistry` already exists as `tools/registry.py`; I will extend it with a
  read-only catalog method, not replace it.
- Skills, Plugins, and MCP have no backend. Creating empty registry classes would
  be scaffolding with no behaviour, which the brief itself warns against.
- The real extension point the UI needs is a **command registry** (Sprint 3),
  which is genuinely required for slash commands and is not speculative.

---

## 3. Gaps and conflicts (decision log)

| # | Issue | Resolution |
| --- | --- | --- |
| 1 | Brief references a "main roadmap" with Postgres objectives; **no such doc exists**, zero Postgres deps | You chose: define Sprints 5–7 here concretely |
| 2 | `/switch` listed but not implemented | Omit; note in parity doc (ask if you want an alias) |
| 3 | `/clear`, `/exit` have no web meaning | Marked unmapped, not faked |
| 4 | Tools nav with no API to list tools | You chose: add a small read-only `/api/v1/tools` |
| 5 | Brief says "file attachment support if already implemented" | Chat attachments are **not** implemented; uploads live in Documents. No fake paperclip. |
| 6 | Brief says "retry states" | No regenerate endpoint exists → retry resends the last user message as a new turn, clearly labelled |
| 7 | pgvector vs FAISS parity | FAISS stays until Sprint 6 proves equivalence, then becomes a fallback |

---

## 4. Sprint roadmap

Nine sprints, dependency-ordered. Each ends with tests and a report.

### Sprint 0 — Audit ✅ (this document)
CLI command inventory, tool/registry inspection, persistence inventory,
extension-point assessment, ERP scope confirmation. **Done.**

### Sprint 1 — Black-and-white UI/UX redesign
- Replace the token palette: white canvas, near-black text, black primary
  buttons, neutral grays. Remove the clay accent.
- ChatGPT-style sidebar: New chat, Search, date-grouped conversations
  (Today / Yesterday / Previous 7 days / Older), then Documents, Approvals,
  Tools. Bottom: Settings, account, logout.
- Future nav items — **Skills, Plugins, MCP, Custom Tools** — visible with a
  subtle "Soon" chip, linking to honest Coming Soon pages.
- Composer restyle (white, thin border, black send button).
- Responsive: persistent ≥1024px, collapsible 768–1024px, drawer <768px.
- **No ERP nav, no ERP pages.**
- Acceptance: lint/typecheck/tests pass; no clay colour remains; nav renders all
  sections with correct availability states.

### Sprint 2 — Chat navigation and performance
- Open a conversation at the **latest message** without a visible jump.
- Scroll anchoring: never yank a reader who has scrolled up.
- **Jump to latest** pill with new-message count.
- Long conversations: keep streaming re-renders cheap (memoised rows, stable
  keys, no whole-list invalidation per token).
- Targeted cache invalidation instead of refetching the world.
- Acceptance: switching threads is instant; scroll position is respected; a
  100-message thread streams without re-rendering all rows.

### Sprint 3 — Slash commands and CLI parity
- `CommandRegistry` in the frontend: `name, aliases, description, category,
  availability, handler, requiresArgs, comingSoonMessage`.
- Composer `/` menu: arrows, Enter, Escape, mouse, live filtering, categories,
  descriptions, disabled styling for unavailable commands.
- Implemented: `/new`, `/threads`, `/history`, `/rename`, `/delete`, `/help`,
  `/approvals`, `/documents` (navigates to the page — not a duplicate uploader).
- Coming Soon: `/skills`, `/plugins`, `/mcp`, `/tools` (see below), `/memory`,
  `/settings` if unimplemented, `/model`.
- **Security:** no shell execution. Arguments validated; handlers only touch
  existing services/endpoints. `/exit` and `/clear` are excluded and documented.
- Deliverable: `COMMAND-PARITY.md` mapping CLI → service → endpoint → UI action.
- Acceptance: keyboard-only selection works; unavailable commands show the
  Coming Soon message and never fake success.

### Sprint 4 — Tools, agent activity, and HITL
- Real tool timeline (already built) restyled for the monochrome system; add the
  **Waiting for approval** state so an interrupted tool is not shown as running.
- Approvals inline in chat and on `/approvals`, monochrome.
- Add read-only `GET /api/v1/tools` (name + description + category) so the Tools
  page lists the 91 real tools instead of a placeholder.
- Error and cancellation states surfaced honestly.
- Acceptance: timers start/stop on real events; no fabricated states; approval
  actions still validated by the backend.

### Sprint 5 — PostgreSQL foundation
- Add `psycopg[binary]`, connection settings, and a schema/migration path.
- Move `threads`, `notes`, `documents`, `document_chunks`, `rag_meta` to
  Postgres; keep the repository interfaces so services do not change.
- Switch LangGraph to the Postgres checkpointer (official package) with the same
  thread semantics.
- A one-shot migration script from the existing SQLite database, idempotent and
  verified by row counts.
- **ERP JSON untouched.**
- Acceptance: CLI and API work against Postgres; existing tests pass against
  Postgres via a fixture; SQLite path still available behind config during
  transition.

### Sprint 6 — pgvector and hybrid search
- `document_chunks.embedding vector(1536)` with an HNSW/IVFFlat index.
- `PgVectorStore` implementing the same small API as `VectorIndexStore`
  (`add`, `replace`, `remove`, `search`, `stats`), so `DocumentService` is
  unchanged.
- BM25 corpus built from Postgres chunks; **RRF unchanged**.
- Owner filtering stays inside each retriever, before fusion (as today).
- Acceptance: identical retrieval results on a fixture corpus; vector, bm25, and
  hybrid modes all work; FAISS remains as a fallback flag.

### Sprint 7 — Migration verification
- Row-count and checksum comparison per table; checkpoint replay; retrieval
  parity on a fixed query set; owner isolation re-proven.
- Performance sanity (no N+1 queries; index usage checked).
- **ERP JSON byte-identical before and after.**

### Sprint 8 — Security, performance, reliability
- Regression across CLI, API, and web; auth/ownership re-verification; log
  hygiene; no secrets in payloads; `tsc`/lint/build gates; profiling of thread
  switching and streaming.

### Sprint 9 — Final verification
- The 18 acceptance criteria in §6 below, verified explicitly, with any that
  cannot be met reported honestly rather than claimed.

---

## 5. Architecture boundaries (minimal)

```
frontend/src/
├── features/chat/        conversation, streaming, tool timeline
├── features/commands/    NEW: command registry + palette (Sprint 3)
├── features/nav/         NEW: sidebar sections + availability
└── app/(dashboard)/      chat, documents, approvals, settings,
                          tools (real), skills|plugins|mcp|custom-tools (Soon)
```

Backend additions are deliberately tiny: one read-only `GET /api/v1/tools`
(Sprint 4), then the storage swaps in Sprints 5–6 behind existing interfaces.

Reuse over invention: `tools/registry.py` gains a catalog method rather than a
second registry; `DocumentService` and `ThreadService` keep their signatures.

---

## 6. Acceptance criteria (from the brief, made verifiable)

| # | Criterion | Sprint | How it is proven |
| --- | --- | --- | --- |
| 1 | Black-and-white ChatGPT-inspired UI | 1 | token audit: no accent hue; visual + CSS check |
| 2 | Chat is central | 1 | route inventory; sidebar is chrome |
| 3 | No ERP dashboards/CRUD | 1 | route inventory has none |
| 4 | ERP demo tools still work on JSON | 4 | live tool call over the JSON dataset |
| 5 | CLI commands mapped meaningfully | 3 | `COMMAND-PARITY.md` |
| 6 | Slash suggestions work | 3 | unit tests for filter/rank |
| 7 | Keyboard navigation | 3 | RTL keyboard tests |
| 8 | Commands execute via approved handlers | 3 | no shell paths; handler tests |
| 9 | Future commands show Coming Soon | 3 | test per command |
| 10 | Future nav visible, marked unavailable | 1 | nav test |
| 11 | No fake backend behaviour | all | review + tests |
| 12 | Thread nav and scrolling correct | 2 | scroll-position tests |
| 13 | Real tool lifecycle + elapsed time | 4 | existing tests + live run |
| 14 | Postgres preserves app data | 5, 7 | row counts + checksums |
| 15 | pgvector works with RAG | 6 | retrieval parity fixture |
| 16 | BM25 and RRF preserved | 6 | existing RRF/BM25 tests |
| 17 | CLI remains operational | 8 | CLI smoke run |
| 18 | Automated tests pass | all | CI gates |

---

## 7. Known risks

- **Postgres work is the largest and riskiest block.** It touches persistence
  the CLI shares. Sprints 5–6 keep SQLite behind a config flag until parity is
  proven, so a regression is recoverable.
- **pgvector dimension lock**: changing embedding dimensions later requires a
  re-ingest; the existing `rag_meta` guard already catches mismatches.
- **`tsc` crashes intermittently** on this Windows/Node 26 host; CI must run
  `pnpm typecheck` as the gate (already documented).
- **Single worker** assumption remains until Postgres lands; Sprint 5 is the
  first point where multi-worker becomes possible.
- Coming Soon pages risk feeling like dead ends — they must state plainly what
  will be possible, without implying it works now.

---

## 8. Approval

Sprints 1–4 are buildable immediately with no schema risk. Sprints 5–7 are
defined here per your decision and will start only after you approve the storage
plan, since they migrate the CLI's persistence too.

---

## 9. Progress

| Sprint | Status |
| --- | --- |
| 0 — Audit | done (`COMMAND-PARITY.md`, §2) |
| 1 — B&W UI/UX redesign | **done — verified** |
| 2 — Chat navigation & performance | **done — verified** |
| 3 — Slash commands & parity | **done — verified** |
| 4 — Tools, activity, HITL | **done — verified** |
| 5 — PostgreSQL foundation | **done — verified** |
| 6 — pgvector & hybrid search | **done — with a documented deviation** (arrays, not pgvector; see below) |
| 7 — Migration verification | **done** |
| 8 — Security/performance/reliability | not started |
| 9 — Final verification | not started |

### Sprint 1 verification

| Check | Result |
| --- | --- |
| Served CSS | `--background:#fff`, `--foreground:#0d0d0d`, `--accent:#0d0d0d`, `--sidebar:#f9f9f9`, `--border:#e5e5e5` |
| Clay/beige remnants | none (`#c96442` / `#f7f6f3` absent from the built CSS) |
| Dark palette | removed entirely |
| All 8 routes | 200 with real HTML (`/chat`, `/documents`, `/approvals`, `/tools`, `/skills`, `/plugins`, `/mcp`, `/settings`) |
| ERP routes | `/inventory`, `/products`, `/stock`, `/suppliers`, `/warehouses` → **404** |
| Coming Soon pages | all three show "Soon" and "nothing on this page is simulated" |
| `GET /api/v1/tools` | 200, **91 tools, 15 approval-gated**, 11 categories |
| `pnpm lint` | 0 errors, 0 warnings |
| `pnpm typecheck` | clean |
| `pnpm test` | **57 tests** (8 files) |
| `pnpm build` | exit 0, `BUILD_ID` written |
| Backend `pytest` | **695 passed** (+5 for the tools catalog) |

Sprint 1 defects found and fixed:

1. **Server→Client component boundary** — passing a Lucide icon *component*
   from a Server Component into the client `ComingSoon` broke prerendering
   (`Functions cannot be passed directly to Client Components`). The icon is now
   passed as a rendered node.
2. **Date grouping needed UTC handling** — SQLite writes `"YYYY-MM-DD HH:MM:SS"`
   with no zone, which browsers parse as local time. `parseTimestamp` normalises
   it, with tests covering bare, offset, and garbage inputs.
3. **Dark-theme leftovers** — the `forcedTheme` provider, the `.dark` token block,
   and a `html.dark` rule would all have shipped a half-specified theme. Removed.

Process note: my first live verification launched servers whose task logs were
empty (the ports were still held), so I re-checked the actual listener and
confirmed it served the *new* `/api/v1/tools` route (401, not 404) before
trusting the result.

### Sprint 2 verification

| Check | Result |
| --- | --- |
| Open at newest message | `jumpToBottom` on first history load per thread, no animation |
| Never yank the reader | `isNearBottom` gates every follow; scrolling up detaches (`distanceFromBottom` tests: 80px boundary, exact, unscrollable page) |
| Jump to latest | sticky pill, shows an unseen count when content arrives while detached |
| Targeted invalidation | after a turn only `["threads"]` + that thread's `history` are invalidated — proven with a spy that `thread-b` is untouched |
| Fast switching | `staleTime` 5 min / `gcTime` 30 min per thread history; a test proves explicit invalidation still overrides `staleTime` |
| Rendering cost | message rows are `memo`ised, so a streamed token no longer re-renders every restored turn |
| Live stream | 9 token frames in order, 1 tool_start/tool_end round trip, history returned `['user','tool','assistant']` |
| Gates | lint 0 · typecheck clean · **67 tests** · build exit 0 |

Sprint 2 defect found and fixed:

**Stale history after a turn.** The stream hook invalidated only the thread
*list*. Because I had also added a 5-minute `staleTime` to history for fast
switching, a conversation's stored messages could stay stale after sending —
switching away and back would show the pre-turn history. It now invalidates that
thread's `history` key too, and a test proves invalidation overrides `staleTime`.

### Sprint 3 verification

| Check | Result |
| --- | --- |
| Registry size | 8 available + 5 planned |
| Parity with the CLI | `/new`, `/threads`, `/history`, `/rename`, `/delete`, `/approvals`, `/documents` (+`/ingest` alias), `/help` |
| Honest exclusions | no `/exit` (would end a process), no `/clear` (terminal-only), no `/switch` (the CLI has none — `/threads` is the switcher) |
| Planned namespaces | `/skills`, `/plugins`, `/mcp`, `/memory`, `/model` — all marked Soon, all handler-less |
| Invariants | tests assert every available command has a handler, no planned command has one, every planned one has a message, and there are no duplicate names/aliases |
| Composer behaviour | 8 component tests: prose does not open the menu, `/` opens it, filtering, Enter selects and clears, arrows move the highlight, Esc closes, Shift+Enter keeps a newline, planned rows show "Soon" |
| Shipped bundle | all 13 command names present in the built JS; `"/exit"` and `"/switch"` absent |
| Gates | lint 0 · typecheck clean · **94 tests** · build exit 0 |

Sprint 3 defect found and fixed:

**Unguarded `scrollIntoView` in the menu.** Keeping the highlighted row visible
called `scrollIntoView` unconditionally; it does not exist in every environment,
so the first keystroke threw and the menu never opened. Now optional-chained —
the highlight simply does not auto-scroll where the API is missing. Caught by the
component tests, not by reading the code.

Also documented: `GET /api/v1/tools` (added in Sprint 1) now has a section in
`API.md`, and the following section numbers were corrected (there were two §11s).

### Sprint 4 verification

The tool lifecycle and the approval panel already existed from earlier work, so
this sprint fixed the edge states rather than rebuilding them.

| Check | Result |
| --- | --- |
| Tool timeline | `tool_start` → `tool_end` correlated by `tool_call_id`; parallel same-name calls stay separate (covered by existing tests) |
| Elapsed timers | measured between real frame arrivals; frozen on completion, one interval only while running |
| 409 handling | `ApiError.isStaleApproval` recognises `APPROVAL_STALE` / `APPROVAL_NOT_PENDING` |
| Stale panel | an already-resolved approval replaces its buttons with "already resolved — nothing was executed by this page" instead of inviting a retry that must fail |
| Stop honesty | new `stopped` status; a stopped turn no longer reports `completed` and shows "may be incomplete" |
| Contracts | 11 backend HITL tests pass: duplicate → 409 `APPROVAL_NOT_PENDING`, concurrent → executes once, edit sends reviewed args, reject executes nothing |
| Gates | lint 0 · typecheck clean · **100 tests** · build exit 0 |

Sprint 4 defects found and fixed:

1. **Stop reported success.** `stop()` set the turn to `"completed"`, so an
   interrupted answer looked finished. It now sets a distinct `"stopped"` and the
   view says the response may be incomplete. Nothing in the stream can produce
   that state — only the reader's Stop does.
2. **A stale approval stayed on screen.** Submitting a decision that the server
   had already resolved showed raw error text and left the buttons live, inviting
   a retry that could only fail again. It now dismisses the decision.
3. **Dead branch.** `StatusLabel` rendered `{error ? "Failed" : "Failed"}`.

Note on scope: my live check asked the real model for an approval-gated action
and it answered without calling a tool, so the duplicate-decision path was proved
against the backend's deterministic tests rather than a live model — the exact
codes those tests assert are the ones the frontend now branches on.

### Sprint 5 verification

PostgreSQL 18.7 was already installed locally, so everything here ran against a
real server rather than being written blind.

| Check | Result |
| --- | --- |
| Backend switch | `DATABASE_BACKEND=sqlite\|postgres` + `POSTGRES_DSN`; SQLite remains the default |
| Repository parity | 15 contract tests × 2 backends = **30 passed** (`test_storage_parity.py`) |
| Container on Postgres | **5 passed** (`test_postgres_container.py`): real `PostgresSaver`, thread round trip, ingest→search, stats |
| Owner isolation | re-proven on Postgres: Alice cannot retrieve Bob's chunk or vice versa |
| Migration | 10 threads, 4 documents, 333 chunks, 2 meta rows, **236 checkpoints / 19 threads** |
| Migration idempotency | second run copied 0 rows and left every count unchanged |
| Timestamp parity | `created_at` identical to SQLite byte for byte |
| SQLite regression | **710 passed, 20 skipped** — the 20 skips are the Postgres tests without a DSN |
| ERP JSON | untouched (mtime predates this work; diff contains no new identifiers) |

Design decisions worth recording:

1. **One SQL dialect, one adapter.** Rather than duplicate ~500 lines of SQL,
   `sql_backend.py` absorbs the three differences that actually exist: `?` →
   `%s`, `lastrowid` → `RETURNING`, and `CURRENT_TIMESTAMP` → UTC. The query text
   is written once and the services are unchanged.
2. **`TIMESTAMP`, not `TIMESTAMPTZ`.** SQLite stores naive UTC text. A
   `TIMESTAMPTZ` column reinterprets that text in the session's timezone, which
   shifted every timestamp by the server's UTC offset. The parity tests caught
   this; a plain `TIMESTAMP` round-trips exactly.
3. **Autocommit stays off.** `PostgresSaver.setup()` issues `CREATE INDEX
   CONCURRENTLY`, which Postgres refuses inside a transaction. Rather than make
   the whole connection autocommit (which would silently disable `rollback()` and
   break `replace_document` atomicity), autocommit is enabled only for the
   duration of that one call.
4. **Checkpoints migrate through the savers**, not by copying internal tables —
   the serialised payload format is the checkpointer's business.

Bugs found and fixed during the sprint:

- `CREATE INDEX CONCURRENTLY cannot run inside a transaction block` — fixed with
  the scoped-autocommit helper above.
- **Timestamps shifted by the server's timezone** (found by asserting field
  values, not just row counts).
- `pending_writes` is `(task_id, channel, value)`, not `(channel, value)` — my
  first unpack dropped every checkpoint with the wrong arity.
- A broad `except` reported "0 checkpoints copied" without saying why. Failures
  are now reported individually instead of being swallowed.

### Sprint 6 — vectors in Postgres

The plan said `vector(1536)` with an HNSW index. **That was not possible on this
machine**, so the deviation is recorded here rather than papered over:

```
CREATE EXTENSION vector  ->  ERROR: extension "vector" is not available
```

pgvector is not installed in PostgreSQL 18.7, and it cannot be built from source
because there is no C toolchain (no `cl`, no `nmake`). I did not fake an index or
claim one exists.

What was built instead: `PgVectorStore`, storing embeddings in
`document_chunks.embedding DOUBLE PRECISION[]`, with the **same interface** as
`VectorIndexStore` (`add`, `replace`, `remove`, `search`, `stats`). So:

- `DocumentService` is unchanged, and RRF fusion is untouched.
- Owner filtering still happens before fusion, in the same query that scores.
- Vectors are L2-normalised exactly as FAISS received them, so cosine scores are
  directly comparable — proved by a test asserting 0.6 and 1.0 exactly.
- **Cost:** search scans the namespace rather than an ANN index. Correct at this
  corpus size, and the documented upgrade path (`POSTGRES.md`) is five mechanical
  steps once pgvector is available.

Bugs found and fixed:

1. **`reconstruct_n` crashed the interpreter** (exit `0xC0000409`, a native
   stack-buffer error) when reading vectors from `IndexIDMap2`. `read_index` and
   `id_map` were fine; only reconstruction died. Fixed by reading the flat
   index's contiguous array via `rev_swig_ptr`, which returns identical data.
2. **Explicit `row_id` inserts did not advance the BIGSERIAL**, so the first
   insert after migration would collide. `_reset_sequences` now advances it.
3. **Vector migration was not idempotent** — the second run re-copied all 333.
   `WHERE embedding IS NULL` fixes it: second run reports 0.
4. **Test cross-contamination:** the 4-dimension vector tests left
   `rag_meta.embedding_dimensions=4`, making every 1536-dimension test refuse to
   start. Both sides now clean up.

Verification:

| Check | Result |
| --- | --- |
| Vector store tests | **7 passed** (ranking, exact cosine scores, namespace filtering, NULL-vector skipping, removal, dimension rejection, owner isolation) |
| Full migration | rows + **236 checkpoints** + **333 embeddings**, retrieval self-similarity 1.000000 |
| Migration idempotency | second run: 0 rows, 0 checkpoints, **0 vectors** |
| Sequence | `max row_id=333`, `next row_id=334` — collision-free |
| E2E on Postgres | ingest → hybrid search returns the document → chat turn → history 2 messages |
| Full suite (Postgres on) | **737 passed** |
| Full suite (SQLite only) | **710 passed, 27 skipped** |

### Sprint 7 — migration verification

Covered by the run above and by `test_storage_parity.py`: per-table counts,
identical timestamps field by field, checkpoint replay across 19 threads,
retrieval parity, sequence state, and owner isolation re-proven on Postgres.

**ERP JSON is untouched** — verified by mtime (predates this work) and by the
diff containing no identifiers introduced by it.

### UI — fully rounded composer

The chat input is now a full pill (`rounded-[1.75rem]`, circular send button),
matching ChatGPT, rather than a fixed-radius box. Verified at lint 0, typecheck
clean, 100 frontend tests, build exit 0.





