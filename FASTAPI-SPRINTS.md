# FastAPI Integration — Sprint Plan

Companion to `ARCHITECTURE.md` §10 and the approved implementation plan. This
document is the working ledger: it sequences the work by dependency, and each
sprint states its goal, deliverables, and exit criteria.

**Status: complete — all 12 sprints done. 685 tests pass; CLI verified.**

---

## Dependency ordering

Sprints are ordered so no sprint depends on a later one:

```
1 Dependencies & config
      │
2 Persistence, ownership columns, connection lock   ◄── the only shared-code sprint
      │
3 User-scoped retrieval (identity → graph → tools → retrievers → before RRF)
      │
4 API foundation (schemas, security, errors, app, lifespan, health)
      │
5 Auth endpoint + protection wiring  ◄── every later router is protected from day one
      │
6 Threads        7 Chat        8 Streaming        9 Approvals        10 Documents + uploads
      │
11 Hardening & full verification
      │
12 Documentation
```

Sprints 1–3 change existing code and must leave the **full 547-test suite green**
before anything is layered on top. Sprint 5 exists before the resource routers so
that each of them is written against a real `CurrentUser` rather than being
retrofitted with auth afterwards.

---

## Sprint 1 — Dependencies & configuration

**Goal** Make FastAPI, multipart parsing, and JWT signing available, and add the
API settings to the existing `Settings` model.

Deliverables
- `uv add fastapi python-multipart pyjwt` → `pyproject.toml` + `uv.lock`
  (no `requirements.txt`).
- `config.py`: `api_env`, `api_host`, `api_port`, `api_upload_path`,
  `api_max_upload_bytes`, `api_keys`, `jwt_secret_key`, `jwt_algorithm`,
  `jwt_access_token_expire_minutes`, `cors_origins`; plus `parse_api_keys()` and
  `parse_cors_origins()` so comma-separated env values are interpreted in one
  place rather than in routers.
- `.env.example`: the API block with placeholders.

Exit criteria
- `uv sync` succeeds; `import fastapi, jwt` works.
- API settings load from the environment and from `.env`; defaults are inert
  (no secret has a working default).
- Full existing suite green.

---

## Sprint 2 — Persistence, ownership, connection lock

**Goal** Give threads and documents an owner, and make concurrent use of the one
shared SQLite connection safe. This is the only sprint that touches shared code.

Deliverables
- `database.py`: `connection_lock(connection)` (keyed by connection identity, so
  a repository built from a bare connection in a test shares the container's
  lock); idempotent `_migrate_threads_owner_id` / `_migrate_documents_owner_id`
  (`ALTER TABLE … ADD COLUMN owner_id TEXT`) mirroring `_migrate_notes_thread_id`;
  `idx_threads_owner`.
- `models.py`: `Thread.owner_id`, `Document.owner_id` — trailing fields with
  `= None`, so existing positional construction keeps working.
- `repository.py`: every public method of all three repositories runs under
  `connection_lock`; owner-aware `create`/`list_all`/`list_documents`/
  `list_namespaces`/`replace_document`; new `authorized_chunk_ids()`.
- `services/thread_service.py`, `services/document_service.py`: `owner_id`
  passthrough (default `None` ⇒ today's behavior) and `get_document()`.
- `container.py`: `thread_lock(thread_id)` for per-conversation serialization.

Why one lock, not one per repository: all three repositories hold **separate
cursors on the same connection** (`repository.py:29,107,188`), so
per-repository locks would not protect a shared transaction — one thread's
`commit()` could commit another's open transaction.

Exit criteria
- Fresh and pre-existing databases both get the columns; re-running is a no-op.
- Ownership filters return only the caller's rows; `owner_id=None` returns
  everything exactly as today.
- Concurrent repository read/write test passes with no `sqlite3.InterfaceError`
  and no lost rows.
- Full existing suite green; CLI unaffected.

---

## Sprint 3 — User-scoped agent retrieval

**Goal** Ensure one user's documents can never enter another user's retrieved
context — in the RAG results themselves, not merely in the REST endpoints.

Deliverables
- `ChatService.get_config/stream_turn/resume_turn/get_pending_interrupt` accept
  `owner_id` and place it in `configurable["rag_owner_id"]` (CLI passes nothing).
- `tools/documents.py`: both tools take the injected `config: RunnableConfig`
  (same mechanism the notes tools already use) and read `rag_owner_id`. The model
  never supplies it, so a prompt-injected `owner_id` argument cannot exist.
- `DocumentService`: owner-aware `_search_namespaces`; `allowed` row-id sets
  computed once per query and applied **inside both retrievers before RRF**
  (filtering after fusion would let a foreign chunk reorder authorized ones);
  candidate over-fetch then trim to `k`.

Exit criteria
- Two users ingest into the same namespace: neither sees the other's chunks, the
  authorized user's results and RRF order are unchanged by the other's presence.
- The tool obeys only the injected config; an `owner_id` in the tool payload is
  rejected/ignored.
- `owner_id=None` reproduces existing retrieval exactly.
- Full existing suite green.

---

## Sprint 4 — API foundation

**Goal** A FastAPI app that starts, owns the container through its lifespan,
validates input, and reports health.

Deliverables
- `api/errors.py` — `APIError` + handlers producing
  `{"error": {"code", "message", "request_id"}}`; unhandled exceptions become a
  fixed 500 and are logged, never returned as traces.
- `api/security.py` — API-key verification (`hmac.compare_digest`), HS256
  access-token issue/decode with expiry, and the HMAC-signed `approval_id`
  (sign + parse).
- `api/dependencies.py` — container/service providers, `CurrentUser`,
  `get_current_user`.
- `api/schemas/*` — request models with `extra="forbid"` (structurally prevents
  a client supplying `owner_id`), response models.
- `api/main.py` — `create_app(settings=None, container_factory=build_container)`,
  lifespan (`anyio.to_thread.run_sync`, `close()` in `finally`), CORS from
  config with wildcard+credentials rejected, `/docs` gated off in production,
  request-ID middleware, exception handlers.
- `api/routers/health.py` — `/health`, `/health/ready` (local checks only).

Exit criteria
- App starts and shuts down; container closed on shutdown; startup failure is
  loud.
- `/health` and `/health/ready` correct, and the readiness payload contains no
  path, key, or DSN.
- Error envelope consistent; validation errors are 422 with field paths.

---

## Sprint 5 — Authentication and protection

**Goal** Issue tokens and make every subsequent router protected by default.

Deliverables
- `api/routers/auth.py` — `POST /api/v1/auth/token`.
- `get_current_user` wired as a router dependency; missing/invalid/expired
  tokens rejected uniformly.
- Tests: absent, malformed, wrong-signature, expired, and valid token.

Exit criteria
- A protected endpoint returns 401 without a token and 200 with one.
- Expired tokens are rejected (no clock-dependent flakiness: the test mints an
  already-expired token).

---

## Sprint 6 — Threads

**Goal** Thread CRUD over `ThreadService`, scoped to the caller.

Deliverables
- `api/schemas/thread.py`, `api/routers/threads.py`: list, get, patch title,
  delete, history.
- Ownership checked via `thread.owner_id`; non-owned IDs return 404 (no
  existence leak).

Exit criteria
- Lifecycle works end to end; cross-user access is 404 on every route; deletion
  still removes checkpoints then metadata via `ThreadService`.

---

## Sprint 7 — Chat (blocking)

**Goal** One message in, one answer out, reusing `ChatService.stream_turn`.

Deliverables
- `api/schemas/chat.py`, `api/routers/chat.py`: create-or-reuse thread,
  ownership check, pending-approval guard (409), join `token` events, surface an
  interrupt as `awaiting_approval` + `approval_id`.
- Per-thread lock held for the turn, released in `finally`.

Exit criteria
- New and existing conversations work; invalid thread 404; LLM failure 500
  `LLM_ERROR`; no LLM logic in the router.

---

## Sprint 8 — Streaming (SSE)

**Goal** Map the existing `TurnEvent` contract to SSE without simulating
streaming.

Deliverables
- `api/sse.py`: `thread`, `status`, `tool_start`, `tool_end`, `token`,
  `approval_required`, `final`, `error`.
- `POST /api/v1/chat/stream`; `approval_token` stripped from every frame; graph
  stream closed on disconnect; per-thread lock released.

Exit criteria
- Frames match the documented format and media type; every event type covered;
  client disconnect leaves no leaked generator; tokens never appear in output.

---

## Sprint 9 — HITL approvals

**Goal** Decide a pending interrupt through the API without a second approval
system and without allowing a forged, stale, or duplicate decision.

Deliverables
- `api/schemas/approval.py`, `api/routers/approvals.py`: list, detail, decision.
- `approval_id` = HMAC over `sub | thread_id | interrupt_id | approval_token`;
  ordered checks: signature → subject → thread ownership → live interrupt
  identity + recomputed token → lock → `resume_turn`.
- `respond` → 422 `DECISION_UNSUPPORTED` (the graph has no such branch; never
  silently mapped to reject).

Exit criteria
- Approve/edit/reject resume the original thread and return the real result.
- Tampered → 400; wrong subject → 403; unowned thread → 404; stale → 409;
  duplicate/ concurrent → exactly one execution; `approval_token` never exposed.

---

## Sprint 10 — Documents and secure upload

**Goal** Document management over `DocumentService` with safe ingestion.

Deliverables
- `api/uploads.py`: chunked size enforcement (abort mid-stream), magic-byte type
  verification beyond the extension, server-generated paths/filenames,
  content-derived dedupe, per-owner ingest lock against duplicate races,
  `finally` cleanup of scratch files.
- `api/schemas/document.py`, `api/routers/documents.py`: upload, list, get,
  delete (FAISS pruned + BM25 invalidated by the service).
- `source` never returned (filesystem path).

Exit criteria
- Valid text/PDF ingested; extension/magic mismatch → 415; oversized → 413 with
  nothing stored; traversal filename harmless; duplicates skipped; failure leaves
  no scratch file and no orphan.

---

## Sprint 11 — Hardening & full verification

**Goal** Prove the whole thing, existing functionality included.

Deliverables
- Request-ID propagation, logging of operational detail without secrets.
- Full suite (`uv run pytest`) and the CLI smoke test.
- Explicit verification: cross-user thread/document/approval **and retrieval**
  isolation; two conversations concurrently; duplicate decision executing once;
  stale approval refused.

Exit criteria
- All measurements reported from actual runs, not asserted.

---

## Sprint 12 — Documentation

**Goal** Make the new interface usable and the architecture honest.

Deliverables
- `README.md`: REST API section — start commands, auth, endpoint table, curl
  examples, env vars, testing.
- `ARCHITECTURE.md` §10 rewritten from "will plug in" to "is plugged in":
  layering diagram, ownership model, `rag_owner_id` propagation, connection
  lock, `approval_id`, concurrency contract, single-worker limitation; add
  `api/` to the layout; update caveats 3 and 5.

Exit criteria
- Docs match the shipped code, including the limitations listed below.

---

## Known limitations to carry into the final report

- **Single uvicorn worker.** Shared connection, `SqliteSaver`, in-process
  FAISS/BM25 caches, and the single-writer inventory JSON.
- **`SqliteSaver`'s internal lock does not compose with `connection_lock`.**
  Mitigated by per-method commits and per-thread serialization; a connection
  pool or Postgres is the real fix.
- Owner-scoped retrieval over-fetches candidates before trimming to `k`.
- `GET /approvals` is O(threads) — one `get_state` read each.
- `respond` unsupported (422).
- Disconnect handling is best-effort.
- Title generation stays synchronous, as in the CLI.
- Not production-ready: no rate limiting, refresh tokens, or HTTPS termination.

---

## Progress log

| Sprint | Status | Notes |
| --- | --- | --- |
| 1 | done | `fastapi 0.163.0`, `python-multipart`, `pyjwt 2.15.1`; 10 API settings + `parse_api_keys`/`parse_cors_origins`. `.env.example` edit denied — API vars documented here instead. |
| 2 | done | `owner_id` on `threads`/`documents` (schema + idempotent migration + indexes); `Thread`/`Document` trailing fields; one `connection_lock` shared by all three repositories (they share a cursor/transaction); `authorized_chunk_ids`; `thread_lock`. 8-thread interleaved write test passes. CLI smoke test clean. |
| 3 | done | `rag_owner_id` flows `ChatService.get_config` → injected `RunnableConfig` → both document tools → `DocumentService.search`, filtered on each ranking **before** RRF via `_rank_vector`/`_rank_bm25`. Original retriever signatures preserved so existing tests/monkeypatches still hold. 14 isolation tests (hybrid/vector/bm25). CLI unchanged. |
| 4 | done | `api/errors.py`, `context.py`, `security.py`, `dependencies.py`, 5 schema modules, `main.py` (`create_app` + lifespan), `routers/health.py`. Local-only readiness; CORS wildcard and placeholder-in-production rejected at startup; request-ID echoed; `/docs` off in production. 15 tests. |
| 5 | done | `routers/auth.py` (`POST /api/v1/auth/token`), constant-time key compare, HS256 issue/decode with expiry, min 32-char secret. Protected-route fixture proves 401 without a token and the subject comes only from the signed token. 12 tests. |
| 6 | done | `routers/threads.py`: list/get/patch/delete/history, all ownership-scoped. Cross-user and unowned threads answer 404 (no existence leak) on all four routes. 14 tests. |
| 7 | done | `routers/chat.py`: create-or-reuse thread, 409 `APPROVAL_PENDING`, `thread_lock` around the turn, interrupt → `awaiting_approval` + `approval_id`. **Fixed a serious bug**: `create_app(settings=...)` ignored its settings and the default factory called `get_settings()`, so API tests were writing to the real `chatbot_memory.db`. Factory now receives settings; regression test added; 18 fixture rows deleted (8 CLI rows untouched). 12 tests. |
| 8 | done | `api/sse.py` + `POST /api/v1/chat/stream`: every `TurnEvent` mapped, `approval_token` stripped, `THREAD_BUSY`, lock released in `finally`, `GeneratorExit` handled. 13 tests. |
| 9 | done | `routers/approvals.py`: list/detail/decision. `approval_id` = HMAC(subject, thread, interrupt_id, graph token); handle validated by matching it against the caller's own live interrupts (ownership and authorization are one check); re-verified under the thread lock. `respond` → 422. 17 tests incl. concurrent double-submit executing once. |
| 10 | done | `api/uploads.py` + `routers/documents.py`: chunked size enforcement (413), magic-byte type check (415), server-generated `<sha>/<digest><ext>` paths, per-owner ingest lock, `finally` cleanup, ingest failure removes the stored file. `source` never returned. API tests now use `FakeEmbeddings` (they had been reaching OpenAI). 18 tests. |
| 11 | verified | Full suite **685 passed** (3 consecutive runs). CLI smoke tested (`/threads`, `/exit`) — 91 tools, clean shutdown. Cross-cutting security tests added (`test_api_security.py`). Live uvicorn run confirmed health/401/422/SSE/CORS over real HTTP. One transient failure traced to the pre-existing `test_working_dataset_remains_valid_after_live_use`, which validates the modified working `inventory_data.json` — not caused by this work. |
| 12 | done | `README.md` "REST API" section (auth, endpoint table, curl, streaming, HITL, documents, limitations); `ARCHITECTURE.md` §10 rewritten as "is plugged in" with §10.1–10.9, `api/` added to the layout, dependency direction, caveat 3/5 updated + Windows `httptools` caveat. |

Baseline before any change: `uv run pytest` → **547 passed**.
Final: **685 passed** (+138), CLI regression verified, migrations applied in
place to the existing database (8 conversations preserved).
