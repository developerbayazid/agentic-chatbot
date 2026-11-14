# BAYAZID AI — Frontend

A Next.js client for the BAYAZID AI assistant, designed as a **Claude-inspired**
white interface: white canvas, warm-gray sidebar, restrained typography, and a
content-first conversation. Dark exists only as an optional preference.

The Python backend (LangChain, LangGraph, FastAPI, SQLite, FAISS/BM25) is the
single source of truth; this app is a thin presentation layer over its REST and
SSE APIs. It contains no business logic and never touches SQLite, FAISS, or
LangGraph directly.

See [`../FRONTEND_IMPLEMENTATION_PLAN.md`](../FRONTEND_IMPLEMENTATION_PLAN.md)
for the sprint history and [`../API.md`](../API.md) for the backend contract.

---

## Design

| Role | Value |
| --- | --- |
| Canvas | `#ffffff` |
| Sidebar | `#f7f6f3` (warm gray) |
| Text | `#1f1e1d` charcoal / `#6b6a67` secondary |
| Border | `#e8e6e1` |
| Accent | `#c96442` (muted clay) |

No gradients, no heavy shadows, no dashboard cards. Typography is Inter with
JetBrains Mono for code; message width is capped around 68ch.

## Technology

| Concern | Choice |
| --- | --- |
| Framework | Next.js 16 (App Router) |
| UI | React 19, TypeScript, Tailwind CSS v4 |
| Components | shadcn/ui-style primitives on Radix, lucide-react icons |
| Server state | TanStack Query 5 |
| Client state | Zustand 5 |
| Validation | Zod 4 |
| Markdown | react-markdown + remark-gfm, react-syntax-highlighter |
| Tests | Vitest + Testing Library (jsdom) |
| Package manager | pnpm |

## Installation

```bash
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev                     # http://localhost:3000
```

The backend must be running:

```bash
# repository root
uv run fastapi dev           # http://127.0.0.1:8000
```

## Environment

Server-side only — **nothing here is a `NEXT_PUBLIC_` variable**.

| Variable | Default | Purpose |
| --- | --- | --- |
| `BACKEND_API_URL` | `http://127.0.0.1:8000` | Where FastAPI listens |

The browser talks only to its own origin; the Next.js BFF forwards to the
backend. Because of that, the backend's `CORS_ORIGINS` is not involved in normal
use (it still matters for direct access, e.g. Swagger).

## Commands

```bash
pnpm dev          # development server with hot reload
pnpm build        # production build
pnpm start        # serve the production build
pnpm lint         # ESLint
pnpm typecheck    # tsc --noEmit
pnpm test         # Vitest (38 unit tests)
pnpm test:watch   # Vitest in watch mode
```

## Authentication flow

The backend issues a short-lived HS256 JWT. Sending that token to the browser as
a readable value would expose it to every script on the page, so the frontend
uses a server-side BFF:

```
browser ──POST /api/auth/login {api_key}──► Next Route Handler
                                             │ POST /api/v1/auth/token
                                             ▼
                                          FastAPI
                                             │ { access_token }
                                Set-Cookie: bayazid_session=…;
                                HttpOnly; SameSite=Lax; Path=/
                                             ▼
browser ◄── { authenticated, subject } ──────┘

browser ──GET /api/backend/api/v1/threads──► proxy Route Handler
                                             │ cookie → Authorization: Bearer
                                             ▼
                                          FastAPI
```

Consequences, by design:

- The JWT **never reaches JavaScript**: no `localStorage`, no client store, no
  `NEXT_PUBLIC_` secret.
- `middleware.ts` redirects unauthenticated requests to `/login`, but that is a
  UX gate only — **the backend re-validates every request** and remains the
  security boundary.
- A `401` from the backend clears the session and returns the user to `/login`
  instead of retrying.
- The proxy forwards `text/event-stream` unbuffered, which is what keeps
  responses progressive.

Sign in with an operator API key (configured in the backend's `API_KEYS`).

## Application architecture

```
src/
├── app/
│   ├── (auth)/login/             sign-in page
│   ├── (dashboard)/              authenticated shell
│   │   ├── chat/                 new conversation
│   │   ├── chat/[threadId]/      existing conversation (from the URL)
│   │   ├── documents/            upload, list, delete
│   │   ├── approvals/            pending human decisions
│   │   └── settings/             theme, session, app info
│   ├── api/
│   │   ├── auth/{login,logout,session}   BFF session routes
│   │   └── backend/[...path]/            authenticated streaming proxy
│   ├── layout.tsx                theme + query providers, toaster
│   └── globals.css               design tokens (dark/light)
├── components/{ui,layout,shared}  presentation only
├── features/{auth,chat,threads,approvals,documents}   domain hooks + components
├── lib/api/                      the only code that speaks HTTP
│   ├── client.ts                 fetch wrapper, errors, abort
│   ├── sse.ts                    incremental SSE frame parser
│   └── errors.ts                 ApiError + message extraction
├── lib/auth/session.ts           cookie read/decode (server only)
├── stores/ui.ts                  ephemeral UI state (sidebar, drawer)
├── types/api.ts                  types mirroring the OpenAPI schemas
└── middleware.ts                 route protection
```

Rules kept throughout:

- **`lib/api` is the only place that calls `fetch`.** Components never do.
- **Server data lives in TanStack Query; Zustand holds UI state only.** Two
  caches that can disagree would be worse than none.
- **Types mirror the backend exactly** (`types/api.ts`). Nothing is inferred at
  a call site.
- **No fabricated agent internals.** Tool activity appears only because the
  backend emits `tool_start` / `tool_end`; processing states come from real
  stream events.

## Tool execution

Tool activity is a first-class part of the conversation, not a spinner.

| State | Trigger |
| --- | --- |
| running | a real `tool_start` frame arrived → spinner + live elapsed clock |
| completed | the matching `tool_end` arrived → clock frozen at its real duration |
| failed | the stream errored, or the result begins with `Error:` |
| cancelled | you pressed Stop while it was running (the turn, not the tool, was stopped) |

Pairing uses the backend's `tool_call_id`, **not** the tool name: LangGraph runs
tool calls concurrently, so two `search_documents` calls in one turn are
distinguishable only by that id. The server sends it in both `tool_start` and
`tool_end` (`TurnEvent.call_id` → SSE `tool_call_id`).

Each row expands to show the tool, start time, duration, a truncated argument
summary, a truncated result, and any error — never a secret or a filesystem path.

## Streaming

`POST /api/backend/api/v1/chat/stream` returns `text/event-stream` with these
frames (see `API.md` §7):

| Event | Drives |
| --- | --- |
| `thread` | the conversation id (a new thread is created by the first message) |
| `status` | processing indicator |
| `tool_start` / `tool_end` | the tool activity list |
| `token` | appended assistant text, rendered as streaming markdown |
| `approval_required` | stops the turn and shows the approval panel |
| `final` | completion and the auto-generated title |
| `error` | user-facing failure (`STREAM_ERROR`, `THREAD_BUSY`) |

`AbortController` is a genuine **Stop**: the backend sees `GeneratorExit`, closes
the graph stream, and releases the conversation lock.

## Markdown safety

`react-markdown` renders to React elements and emits no raw HTML, so no
sanitizer is needed and `dangerouslySetInnerHTML` is never used. Links are
restricted to `http(s)`, `mailto`, same-origin paths, and fragments, so a
`javascript:` URL cannot be produced (`sanitizeHref`, unit-tested).

## Known limitations

- The session cookie carries the JWT; there is no server-side revocation list, so
  logging out elsewhere does not invalidate it before expiry.
- No conversation search endpoint → the sidebar filters the already-loaded list.
- No regenerate endpoint (it would duplicate a turn), no pagination, and no
  upload-progress events (only bytes sent).
- `POST /chat` buffers the whole answer; only `/chat/stream` is progressive.
- The backend runs one worker, so two tabs on the same conversation can hit
  `THREAD_BUSY`.
- Approvals are bound to a live interrupt: one already decided in the CLI returns
  `409` here.
