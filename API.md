# REST API

BAYAZID AI exposes its existing services over HTTP. The API is a *presentation
layer*: every endpoint calls the same `ChatService`, `ThreadService`,
`DocumentService`, and compiled LangGraph that the CLI drives. There is no
business logic in `api/`.

- **Base URL** — `http://127.0.0.1:8000` by default (`API_HOST` / `API_PORT`).
- **Interactive docs** — `/docs` (Swagger), `/redoc` (ReDoc),
  `/openapi.json`. All three are disabled when `API_ENV=production`.
- **Source** — `src/agentic_chatbot/api/`. Architecture: `ARCHITECTURE.md` §10.

---

## 1. Quick start

```bash
uv sync

# .env needs API_KEYS and JWT_SECRET_KEY (see §2)
uv run fastapi dev            # auto-reload, discovers the root main.py
uv run fastapi run            # production-style
uv run agentic-chatbot-api    # honours API_HOST / API_PORT
```

Then:

```bash
export BASE=http://127.0.0.1:8000

# 1. exchange an API key for a short-lived JWT
export TOKEN=$(curl -s -X POST $BASE/api/v1/auth/token \
  -H 'content-type: application/json' \
  -d '{"api_key":"replace-me-alice"}' | jq -r .access_token)

# 2. use the JWT
curl -s -X POST $BASE/api/v1/chat \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"message":"Hello, how are you?"}'
```

```json
{
  "thread_id": "0f9c5a2e-6c0b-4d55-9d0a-1b2c3d4e5f60",
  "response": "Hello! How can I help you today?",
  "status": "completed",
  "title": "Simple Greetings",
  "approval_id": null
}
```

---

## 2. Authentication

### 2.1 Three different values — do not confuse them

| Value | Where it lives | What you do with it |
| --- | --- | --- |
| API key, e.g. `replace-me-alice` | `API_KEYS` in `.env` (server) | send it **once** in the body of `POST /auth/token` |
| Access token, e.g. `eyJhbGciOi…` | response body | send it as `Authorization: Bearer <token>` |
| `JWT_SECRET_KEY` | `.env` (server only) | **never send it anywhere**; the server signs/verifies with it |

`JWT_SECRET_KEY` is a signing secret, not a credential. Sending it as a bearer
token produces exactly:

```json
{ "error": { "code": "UNAUTHORIZED", "message": "Invalid access token." } }
```

### 2.2 Obtaining a token

`POST /api/v1/auth/token`

```json
{ "api_key": "replace-me-alice" }
```

| Field | Type | Rules |
| --- | --- | --- |
| `api_key` | string | 1–256 chars |

**200**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

- The token is an HS256 JWT carrying `sub` (the operator name), `iat`, and
  `exp`. Lifetime is `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default 1800 s).
- Keys are compared with `hmac.compare_digest`, in constant time.
- **401 `INVALID_CREDENTIALS`** for an unknown key. The message never reveals
  which part was wrong.

### 2.3 Using a token

```
Authorization: Bearer <access_token>
```

- Header names are case-insensitive (`authorization` works).
- The scheme must be `Bearer` followed by a space. `Token …`,
  `Bearer<token>`, or a bare token are not credentials.
- Every resource endpoint requires it. Only `/health`, `/health/ready`, `/docs`,
  `/redoc`, `/openapi.json`, and `POST /auth/token` are unauthenticated.
- The subject is taken **only** from the signed token. No endpoint accepts an
  owner/identity from the request body — unknown fields are rejected (§4.2).

### 2.4 Token failures

All are `401` with `WWW-Authenticate: Bearer`:

| `error.message` | Cause |
| --- | --- |
| `A bearer token is required.` | header missing, empty, wrong scheme, or bare value without `Bearer ` |
| `Invalid access token.` | signature mismatch, expired-by-clock-skew malformed JWT, missing `sub`, **or a non-JWT value such as the signing secret** |
| `Access token has expired.` | past `exp` |

A JWT is valid only against the secret that signed it. Editing
`JWT_SECRET_KEY` (or restarting with a different `.env`) invalidates every token
already issued. There is no refresh endpoint: obtain a new token.

---

## 3. Conventions

### 3.1 Versioning and paths

Business endpoints are under `/api/v1`. Health sits outside the version prefix.
Paths are exact — `POST /api/v1/chat` is not the same as `/api/v1/chat/`
(the trailing slash answers `307`, and some clients drop the `Authorization`
header on that redirect, which then looks like a spurious 401).

### 3.2 Error envelope

Every failure — validation, auth, business, or unexpected — uses one shape:

```json
{
  "error": {
    "code": "THREAD_NOT_FOUND",
    "message": "The requested conversation was not found.",
    "request_id": "f128e34251df4e88a865ce6a54d3dc78"
  }
}
```

`request_id` is also returned in the `X-Request-ID` response header; send your
own to have it echoed and to correlate logs. Stack traces and provider errors
are logged, never returned.

### 3.3 Status codes

| Code | Used for |
| --- | --- |
| `200` | success |
| `201` | document uploaded and indexed |
| `204` | deleted (no body) |
| `400` | malformed approval id |
| `401` | missing / invalid / expired token, bad API key |
| `404` | unknown **or not-owned** resource |
| `409` | approval pending, stale, or already decided |
| `413` | upload exceeds the size limit |
| `415` | unsupported file type or invalid content |
| `422` | schema validation, unsupported decision, ingest failure |
| `500` | unexpected server failure |
| `503` | not ready (startup incomplete) |

### 3.4 Strict request bodies

Every request model uses `extra="forbid"`. An unknown field is a `422`, not
silently ignored:

```json
{ "message": "hi", "owner_id": "bob" }
```
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Invalid request: owner_id" } }
```

Identity is derived from the token, so this is a structural guarantee, not a
convention.

### 3.5 Ownership

`threads` and `documents` have a nullable `owner_id`. Resources created through
the API belong to the token subject. A resource that exists but belongs to
someone else answers **404**, never `403` — otherwise the response would confirm
that an ID exists. CLI-created rows (`owner_id = NULL`) are invisible to the API.

---

## 4. Health

### `GET /health`

Unauthenticated liveness probe.

```json
{ "status": "ok", "application": "BAYAZID AI" }
```

### `GET /health/ready`

Unauthenticated. Local, cheap checks only — **no model call, no embedding, no
index read**. No paths, keys, or DSNs are exposed.

**200**

```json
{
  "status": "ready",
  "application": "BAYAZID AI",
  "checks": { "database": true, "graph": true, "storage": true, "configuration": true }
}
```

**503** when anything fails (`status: "not_ready"`), e.g. a placeholder
`JWT_SECRET_KEY`:

```json
{
  "status": "not_ready",
  "application": "BAYAZID AI",
  "checks": { "database": true, "graph": true, "storage": true, "configuration": false }
}
```

`configuration` requires a non-placeholder signing secret of ≥32 chars,
parseable `API_KEYS`, and an OpenAI key.

---

## 5. Chat

### `POST /api/v1/chat`

Send one message and wait for the whole answer.

| Field | Type | Rules |
| --- | --- | --- |
| `message` | string | 1–32 000 chars, not blank |
| `thread_id` | string \| null | omit, `null`, `""`, or whitespace to **start a new conversation**; otherwise an existing ID you own |

```json
{ "message": "Summarise the handbook", "thread_id": null }
```

Create a new conversation by sending **no usable `thread_id`** — omit the field,
send `null`, or send an empty string from a form. The response returns the new
`thread_id`; send that back to continue the same conversation. Any non-blank
value is treated as an existing ID you must own:

| `thread_id` sent | Result |
| --- | --- |
| omitted, `null`, `""`, `"   "` | new conversation, `200` |
| a real ID you own | continues it, `200` |
| an unknown / someone else's ID | `404 THREAD_NOT_FOUND` |

**200 — completed**

```json
{
  "thread_id": "0f9c5a2e-6c0b-4d55-9d0a-1b2c3d4e5f60",
  "response": "The handbook covers onboarding, policies, and expenses.",
  "status": "completed",
  "title": "Handbook Summary",
  "approval_id": null
}
```

**200 — stopped for human approval**

```json
{
  "thread_id": "0f9c…",
  "response": "",
  "status": "awaiting_approval",
  "title": null,
  "approval_id": "3Qa9x…"
}
```

See §8 for the approval flow.

Failures: `404 THREAD_NOT_FOUND` (unknown or not owned),
`409 APPROVAL_PENDING` (a previous action is still undecided — decide it first),
`422 VALIDATION_ERROR`, `500 INTERNAL_ERROR`.

`title` is generated on the first turn only. The turn is serialized per
conversation; concurrent requests on *different* threads run in parallel.

### `POST /api/v1/chat/stream`

Identical request and rules, answered as Server-Sent Events instead of JSON.
See §7.

---

## 6. Threads

All routes are scoped to the caller. `{thread_id}` for another user answers
`404`.

| Method | Path | Success |
| --- | --- | --- |
| `GET` | `/api/v1/threads` | `200` |
| `GET` | `/api/v1/threads/{thread_id}` | `200` |
| `PATCH` | `/api/v1/threads/{thread_id}` | `200` |
| `DELETE` | `/api/v1/threads/{thread_id}` | `204` |
| `GET` | `/api/v1/threads/{thread_id}/history` | `200` |

### `GET /api/v1/threads`

```json
{
  "threads": [
    {
      "thread_id": "0f9c…",
      "title": "Handbook Summary",
      "created_at": "2026-11-14 19:21:47",
      "updated_at": "2026-11-14 19:38:24"
    }
  ]
}
```

Ordered by `updated_at` descending. Threads are created by sending a message —
there is no `POST /threads`.

### `GET /api/v1/threads/{thread_id}`

```json
{
  "thread_id": "0f9c…",
  "title": "Handbook Summary",
  "created_at": "2026-11-14 19:21:47",
  "updated_at": "2026-11-14 19:38:24"
}
```

### `PATCH /api/v1/threads/{thread_id}`

```json
{ "title": "A much better title" }
```

`title` is 1–100 chars (stored truncated to 100). Returns the updated thread.

### `DELETE /api/v1/threads/{thread_id}`

`204` with no body. Removes the LangGraph checkpoints **and** the metadata, so
no orphaned message state remains. Deleting twice → `404`.

### `GET /api/v1/threads/{thread_id}/history`

```json
{
  "thread_id": "0f9c…",
  "messages": [
    { "role": "user", "content": "Hello" },
    { "role": "tool", "content": "calculator: 4" },
    { "role": "assistant", "content": "It is 4." }
  ]
}
```

`role` is `user`, `assistant`, or `tool`. Tool content is summarized (first 500
chars of the tool result) — raw internal graph state is never exposed.

---

## 7. Streaming (SSE)

`POST /api/v1/chat/stream` → `200`, `content-type: text/event-stream`,
`cache-control: no-cache`, `x-accel-buffering: no`.

```bash
curl -N -X POST $BASE/api/v1/chat/stream \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"message":"Summarise the handbook"}'
```

Each frame is `event: <name>` then `data: <json>`, separated by a blank line.

| Event | `data` | When |
| --- | --- | --- |
| `thread` | `{"thread_id": "..."}` | always first |
| `status` | `{"status": "processing"}` | always second |
| `tool_start` | `{"tool": "search_documents", "arguments": {...}, "tool_call_id": "call_abc"}` | model requests a tool |
| `tool_end` | `{"tool": "search_documents", "result": "...", "tool_call_id": "call_abc"}` | tool returns |
| `token` | `{"content": "Hello"}` | incremental assistant text |
| `approval_required` | see §8.2 | graph paused for a human |
| `final` | `{"title": "..."}` | turn finished |
| `error` | `{"code": "STREAM_ERROR", "message": "..."}` | stream failed |

`token` frames are the model provider's own chunks — genuine streaming, never a
finished answer split into pieces. `approval_token` is stripped from every frame.

```
event: thread
data: {"thread_id": "0f9c…"}

event: status
data: {"status": "processing"}

event: tool_start
data: {"tool": "search_documents", "arguments": {"query": "handbook"}}

event: tool_end
data: {"tool": "search_documents", "result": "{…}"}

event: token
data: {"content": "The "}

event: token
data: {"content": "handbook "}

event: final
data: {"title": "Handbook Summary"}
```

Notes:
- A stream-level failure is an `error` **frame**, not a non-200 status, because
  the headers are already sent. HTTP-level failures (401, 404, 409, 422) are
  normal before streaming starts.
- Closing the connection cancels the turn and releases the conversation lock.
- `THREAD_BUSY` is emitted if another request already drives that conversation:

  ```
  event: error
  data: {"code": "THREAD_BUSY", "message": "This conversation is busy."}
  ```

---

## 8. Human-in-the-loop approvals

Sensitive tools (inventory mutations) never execute on the model's word. The
graph interrupts, the turn stops, and a human decides through the API. This is
the same LangGraph interrupt the CLI shows — there is no second approval system.

### 8.1 The flow

```
1. POST /chat or /chat/stream
       └─► status "awaiting_approval" + approval_id     (nothing executed)
2. GET  /approvals                    → what is waiting
3. GET  /approvals/{approval_id}      → arguments + editable fields
4. POST /approvals/{approval_id}/decision
       └─► the original turn resumes on the same thread
```

### 8.2 `approval_required` in a stream

```
event: approval_required
data: {
  "approval_id": "3Qa9x…",
  "thread_id": "0f9c…",
  "action": "update_product",
  "title": "Update Product",
  "arguments": { "product_id": "PRD-1001", "selling_price": 95000 },
  "details": [["Product", "Latitude Business Laptop 14"], ["Proposed Selling Price", "BDT 95,000"]],
  "warnings": [],
  "allowed_decisions": ["approve", "edit", "reject"]
}
```

### `GET /api/v1/approvals`

The caller's pending approvals. Reads checkpointer state for each of the caller's
threads, so cost is O(threads).

```json
[
  {
    "approval_id": "3Qa9x…",
    "thread_id": "0f9c…",
    "action": "update_product",
    "title": "Update Product",
    "arguments": { "product_id": "PRD-1001", "selling_price": 95000 },
    "allowed_decisions": ["approve", "edit", "reject"]
  }
]
```

### `GET /api/v1/approvals/{approval_id}`

Adds what a UI needs to build an edit form:

```json
{
  "approval_id": "3Qa9x…",
  "thread_id": "0f9c…",
  "action": "update_product",
  "title": "Update Product",
  "arguments": { "product_id": "PRD-1001", "selling_price": 95000 },
  "allowed_decisions": ["approve", "edit", "reject"],
  "tool_call_id": "call-1",
  "editable_fields": ["product_id", "selling_price"],
  "field_types": { "product_id": "string", "selling_price": "integer" },
  "details": [["Current Selling Price", "BDT 89,500"], ["Proposed Selling Price", "BDT 95,000"]],
  "warnings": [],
  "requested_by": "AI Agent",
  "reason": "The agent requested a sensitive inventory operation."
}
```

`404 APPROVAL_NOT_FOUND` if it is not pending for the caller.

### `POST /api/v1/approvals/{approval_id}/decision`

| Field | Type | Rules |
| --- | --- | --- |
| `decision` | `"approve"` \| `"edit"` \| `"reject"` | required |
| `edited_arguments` | object | **required** for `edit`, forbidden otherwise |
| `comment` | string \| null | ≤2000 chars |

```json
{ "decision": "approve", "comment": "Looks right." }
```
```json
{ "decision": "edit", "edited_arguments": { "selling_price": 95000 } }
```
```json
{ "decision": "reject", "comment": "The proposed price is incorrect." }
```

**200**

```json
{
  "approval_id": "3Qa9x…",
  "thread_id": "0f9c…",
  "status": "completed",
  "response": "The price is now BDT 95,000.",
  "title": null,
  "next_approval_id": null
}
```

If the resumed turn proposes another sensitive action, `status` is
`awaiting_approval`, `next_approval_id` is set, and a new decision is required.

**`respond` is not supported.** `{ "decision": "respond", … }` → `422` (the
graph has no such branch; mapping free text onto a rejection would misreport
what the human decided).

### 8.3 Why a decision cannot be forged, replayed, or duplicated

`approval_id` is an HMAC over `subject | thread_id | live interrupt id | the
graph's own approval token`, keyed by `JWT_SECRET_KEY`. It is deterministic,
unforgeable, and names one exact proposal. The graph's token is never returned
to clients.

On every decision the server requires, in order:

1. the handle parses (`400 APPROVAL_INVALID` otherwise);
2. it matches one of **the caller's currently pending** interrupts — so
   ownership and authorization are one check, not two (`409 APPROVAL_NOT_PENDING`);
3. it still matches after re-reading the interrupt **under the conversation
   lock** (`409 APPROVAL_STALE` if the proposal changed).

Consequences:

- A stale handle cannot execute a tool.
- A replayed or concurrent duplicate decision executes **once**; the rest get
  `409`.
- The token is taken from the live interrupt, never from the request, so a
  client cannot decide a different proposal than the one it was shown.

| Code | Status |
| --- | --- |
| `APPROVAL_INVALID` | 400 |
| `APPROVAL_NOT_FOUND` | 404 |
| `APPROVAL_NOT_PENDING` | 409 |
| `APPROVAL_STALE` | 409 |
| `INVALID_DECISION` | 422 |

---

## 9. Documents

Uploads are indexed into the caller's own namespace (`u_<subject>`) and owned by
the caller. Retrieval used by the agent (`search_documents`) is scoped to the
same subject, so one user's documents cannot enter another user's context.

| Method | Path | Success |
| --- | --- | --- |
| `GET` | `/api/v1/documents` | `200` |
| `POST` | `/api/v1/documents` | `201` |
| `GET` | `/api/v1/documents/{doc_id}` | `200` |
| `DELETE` | `/api/v1/documents/{doc_id}` | `204` |

### `POST /api/v1/documents`

`multipart/form-data` with a `file` field. Accepted: `.md`, `.markdown`,
`.txt`, `.rst`, `.pdf`.

```bash
curl -s -X POST $BASE/api/v1/documents \
  -H "authorization: Bearer $TOKEN" \
  -F 'file=@docs/handbook.md'
```

**201**

```json
{
  "document": {
    "doc_id": "9b1d…",
    "title": "handbook",
    "namespace": "u_alice",
    "size_bytes": 412,
    "created_at": "2026-11-14 19:40:02",
    "updated_at": "2026-11-14 19:40:02"
  },
  "chunks_created": 3,
  "skipped": false,
  "warning": null
}
```

Server-side validation:

| Check | Failure |
| --- | --- |
| extension in the allowed set | `415 UNSUPPORTED_FILE_TYPE` |
| size, enforced **while receiving** | `413 FILE_TOO_LARGE` |
| non-empty | `415 EMPTY_FILE` |
| `.pdf` must begin with `%PDF-` | `415 UNSUPPORTED_FILE_TYPE` |
| text must be UTF-8 without NUL bytes | `415 UNSUPPORTED_FILE_TYPE` |
| ingestion succeeded | `422 INGEST_FAILED` |

- The stored path is generated by the server (`<subject>/<sha256[:16]><ext>`); no
  client-supplied path is ever used, so `../../x.md` is harmless.
- Because the name derives from the content, re-uploading identical bytes
  returns `skipped: true` instead of duplicating.
- A failed ingestion deletes the stored file; no orphan survives.
- `source` is a server path and is never returned.

### `GET /api/v1/documents`

```json
{
  "documents": [
    { "doc_id": "9b1d…", "title": "handbook", "namespace": "u_alice", "size_bytes": 412,
      "created_at": "2026-11-14 19:40:02", "updated_at": "2026-11-14 19:40:02" }
  ],
  "namespaces": ["u_alice"]
}
```

### `GET /api/v1/documents/{doc_id}`

One document, same shape. `404 DOCUMENT_NOT_FOUND` if unknown or not owned.

### `DELETE /api/v1/documents/{doc_id}`

`204`. Removes the SQL rows, prunes the document's FAISS entries, and
invalidates the namespace's BM25 cache, so search cannot return a deleted chunk.

---

## 10. Tools

### `GET /api/v1/tools`

The catalog of tools the assistant can call. Read-only and deliberately narrow:
names, categories, and whether each one requires approval. It exposes no
arguments, prompts, or internals, and listing a tool is not permission to run it
— execution still happens only inside a graph turn.

```bash
curl http://127.0.0.1:8000/api/v1/tools \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "count": 91,
  "tools": [
    {
      "name": "calculator",
      "description": "Evaluate a basic arithmetic expression.",
      "category": "Math",
      "requires_approval": false
    },
    {
      "name": "create_expense",
      "description": "Record an expense against the demo inventory dataset.",
      "category": "Inventory (demo)",
      "requires_approval": true
    }
  ]
}
```

`requires_approval` is read from the same policy set the graph enforces
(`SENSITIVE_TOOLS`), so the flag cannot drift from the gate that actually blocks
the call. Descriptions are the first line of the tool's own docstring, truncated
to 300 characters.

Categories: `Math`, `Utility`, `Web`, `Finance`, `Communication`, `Calendar`,
`Text`, `Lifestyle`, `Notes`, `Documents`, `Inventory (demo)`.

---

## 11. Error codes

| Code | Status | Meaning |
| --- | --- | --- |
| `UNAUTHORIZED` | 401 | token missing, invalid, expired |
| `INVALID_CREDENTIALS` | 401 | unknown API key |
| `VALIDATION_ERROR` | 422 | body/query failed schema validation |
| `THREAD_NOT_FOUND` | 404 | unknown or not owned |
| `APPROVAL_PENDING` | 409 | decide the outstanding action before a new message |
| `APPROVAL_INVALID` | 400 | malformed approval id |
| `APPROVAL_NOT_FOUND` | 404 | no pending approval matches |
| `APPROVAL_NOT_PENDING` | 409 | already decided, or another user's |
| `APPROVAL_STALE` | 409 | the proposal changed; request a fresh approval |
| `INVALID_DECISION` | 422 | edit without `edited_arguments`, or arguments on a non-edit |
| `DOCUMENT_NOT_FOUND` | 404 | unknown or not owned |
| `UNSUPPORTED_FILE_TYPE` | 415 | extension or content rejected |
| `FILE_TOO_LARGE` | 413 | exceeds the limit |
| `EMPTY_FILE` | 415 | zero bytes |
| `INGEST_FAILED` | 422 | document could not be indexed |
| `NOT_READY` | 503 | app still starting |
| `INTERNAL_ERROR` | 500 | unexpected failure (details only in logs) |

Stream-only codes, delivered as `error` frames: `STREAM_ERROR`, `THREAD_BUSY`.

---

## 12. Complete curl walkthrough

```bash
BASE=http://127.0.0.1:8000
TOKEN=$(curl -s -X POST $BASE/api/v1/auth/token \
  -H 'content-type: application/json' -d '{"api_key":"replace-me-alice"}' | jq -r .access_token)
AUTH="authorization: Bearer $TOKEN"

# health
curl -s $BASE/health; echo
curl -s $BASE/health/ready | jq '.checks'; echo

# upload a document, then ask about it
curl -s -X POST $BASE/api/v1/documents -H "$AUTH" -F 'file=@docs/handbook.md' | jq .document.title
curl -s -X POST $BASE/api/v1/chat -H "$AUTH" -H 'content-type: application/json' \
  -d '{"message":"What does the handbook say about onboarding?"}' | jq .
THREAD=$(curl -s $BASE/api/v1/threads -H "$AUTH" | jq -r '.threads[0].thread_id')

# continue that conversation
curl -s -X POST $BASE/api/v1/chat -H "$AUTH" -H 'content-type: application/json' \
  -d "{\"message\":\"And about expenses?\",\"thread_id\":\"$THREAD\"}" | jq .response

# history and rename
curl -s $BASE/api/v1/threads/$THREAD/history -H "$AUTH" | jq '.messages | length'
curl -s -X PATCH $BASE/api/v1/threads/$THREAD -H "$AUTH" \
  -H 'content-type: application/json' -d '{"title":"Handbook Q&A"}' | jq .title

# stream a turn
curl -N -X POST $BASE/api/v1/chat/stream -H "$AUTH" -H 'content-type: application/json' \
  -d '{"message":"Say hello in three words"}'

# HITL: propose a sensitive change, then approve it
curl -s -X POST $BASE/api/v1/chat/stream -H "$AUTH" -H 'content-type: application/json' \
  -d '{"message":"Increase the selling price of PRD-1001 to 95000"}'
APPROVAL=$(curl -s $BASE/api/v1/approvals -H "$AUTH" | jq -r '.[0].approval_id')
curl -s -X POST $BASE/api/v1/approvals/$APPROVAL/decision -H "$AUTH" \
  -H 'content-type: application/json' -d '{"decision":"approve"}' | jq .

# clean up
curl -s -X DELETE $BASE/api/v1/threads/$THREAD -H "$AUTH" -o /dev/null -w '%{http_code}\n'
```

---

## 13. Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `API_ENV` | `development` | `production` disables `/docs`, `/redoc`, `/openapi.json` and requires a real secret |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8000` | bind address for `agentic-chatbot-api` |
| `API_KEYS` | *(empty)* | `name=secret,name=secret`; empty ⇒ no key can log in |
| `JWT_SECRET_KEY` | *(none)* | ≥32 chars in practice; required in production |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | |
| `CORS_ORIGINS` | `http://localhost:3000` | comma-separated **explicit** origins; a wildcard is rejected at startup |
| `API_UPLOAD_PATH` | `data/uploads` | where uploads are stored |
| `API_MAX_UPLOAD_BYTES` | `20000000` | upload cap (also bounded by the RAG limits) |

Generate real secrets before deploying:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

A dev profile is enough to explore locally — replace both values with your own
before using it:

```env
API_ENV=development
API_KEYS=alice=replace-me-alice,bob=replace-me-bob
JWT_SECRET_KEY=replace-with-48-random-urlsafe-characters-from-secrets
CORS_ORIGINS=http://localhost:3000
```

Startup refuses to serve if `CORS_ORIGINS` contains `*` (with credentials
enabled), if a production secret is missing/placeholder, or if a configured
secret is shorter than 32 characters.

---

## 14. Deployment and concurrency limits

- **Run exactly one worker.** The app holds one SQLite connection, one
  `SqliteSaver`, in-process FAISS/BM25 caches, and the single-writer inventory
  JSON. SQL is serialized through one connection lock and each conversation
  through a per-thread lock — both are in-process, so a second worker would
  break them.
- `GET /approvals` is O(threads).
- No rate limiting, no refresh tokens, no HTTPS termination. Do not expose this
  directly to the internet.
- On Windows, `uvicorn[standard]`'s `httptools` can crash at startup
  (`0xC0000005`); use `--http h11` if that happens.

---

## 15. Testing

```bash
uv run pytest                          # whole suite (no OpenAI calls)
uv run pytest tests/test_api_auth.py -q
uv run pytest tests/test_api_isolation.py tests/test_api_approvals.py -q
```

API tests use `TestClient` with a temporary database, temporary FAISS directory,
copy of the inventory seed, and deterministic fake embeddings. They assert
cross-user isolation, concurrent-decision safety, upload rejection, SSE frames,
and that no response ever contains an `approval_token`.

---

## 16. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `401 Invalid access token.` | sent `JWT_SECRET_KEY` or a truncated JWT | use the `access_token` from `/auth/token` |
| `401 A bearer token is required.` | header missing, or not `Bearer <token>` | exactly `Authorization: Bearer <access_token>` |
| `401 Access token has expired.` | older than `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, or `JWT_SECRET_KEY` changed | obtain a new token |
| `401` only on one endpoint, with a trailing slash | `307` redirect dropped `Authorization` | call the exact path (`/api/v1/chat`) |
| `422 Invalid request: ` (empty field list) | called `POST /chat` with **no** body | send `-H 'content-type: application/json' -d '{...}'` |
| `422 Invalid request: message, nope` | unknown field (e.g. `owner_id`) | remove it; identity comes from the token |
| `404 THREAD_NOT_FOUND` | unknown thread, or another user's | omit `thread_id` (or send `""`) to start a new conversation |
| `409 APPROVAL_PENDING` | an earlier turn is waiting for a decision | `GET /approvals`, then decide |
| `/health/ready` is `503` | missing `API_KEYS` / weak `JWT_SECRET_KEY` | set them in `.env` |
| `uv run fastapi dev` finds no app | the CLI looks in the **current** directory | run it from the repo root (root `main.py`), or use `--entrypoint main:app` |
