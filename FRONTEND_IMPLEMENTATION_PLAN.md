# BAYAZID AI — Frontend Implementation Plan

Status: **Sprints F1–F3 in progress.**
Companion documents: `API.md` (backend contract), `ARCHITECTURE.md` §10.

> **Design direction (supersedes the earlier dark-first plan).** The interface is
> **Claude-inspired**: white background, minimal chrome, warm-gray sidebar,
> elegant typography, generous whitespace, and a content-first conversation. Dark
> is *not* the default and does not influence the primary implementation.

---

## 1. Project overview

The Python backend (LangChain, LangGraph, FastAPI, SQLite, FAISS/BM25) is the
single source of truth. This frontend is a presentation layer over its REST and
SSE APIs: no business logic, no second persistence layer, no direct database or
model access. The CLI is untouched.

---

## 2. Verified backend contract

Derived from the live `app.openapi()` (17 paths / 18 operations) and
`api/sse.py`, not from assumptions.

### 2.1 SSE events (the only ones that exist)

| Event | Payload | Meaning |
| --- | --- | --- |
| `thread` | `{thread_id}` | conversation id (created by the first message) |
| `status` | `{status:"processing"}` | turn accepted |
| `tool_start` | `{tool, arguments}` | the model requested a tool |
| `tool_end` | `{tool, result}` | the tool returned |
| `token` | `{content}` | incremental assistant text |
| `approval_required` | `{approval_id, thread_id, action, title, arguments, details, warnings, allowed_decisions}` | graph paused for a human |
| `final` | `{title}` | turn finished |
| `error` | `{code, message}` | `STREAM_ERROR` or `THREAD_BUSY` |

### 2.2 Tool lifecycle — verified, with one gap

`ChatService._events_from_chunk` emits `tool_call` from the `chat_node` update
(before execution) and `tool_result` from the `tools`/`approval` update (after).
**Real tool timers are therefore legitimate, not fabricated.**

Gap found by probing a two-call turn: **neither event carries a correlation id**,
and LangGraph executes tool calls concurrently. Two parallel
`search_documents` calls produce two `tool_start`s and two `tool_end`s that
cannot be paired reliably.

Minimal, backward-compatible enhancement (additive field, no event rename):

- `TurnEvent.call_id` → forwarded as `tool_call_id` in the `tool_start` and
  `tool_end` payloads.
- Existing consumers ignore it; the CLI is unaffected.

Without it the UI would have to guess, which would fabricate pairing.

### 2.3 Backend gaps carried forward

| Gap | Consequence |
| --- | --- |
| No per-tool `failed` event | a tool that raises inside `ToolNode` surfaces as an error/turn failure, not `tool_end{failed}`. UI shows Failed only when the backend says so. |
| No `cancelled` tool event | Stop aborts the whole turn; running tools are shown as **Cancelled** (client truth), never as completed. |
| No tool start/finish timestamps | elapsed time is measured client-side from the real event arrival times. |
| No conversation search endpoint | sidebar filters the loaded list. |
| No regenerate endpoint | omitted. |

---

## 3. Design system — Claude-inspired, white-first

| Role | Value |
| --- | --- |
| Main background | `#ffffff` |
| Sidebar | warm gray `#f7f6f3` |
| Chat background | white |
| Primary text | charcoal `#1f1e1d` |
| Secondary text | neutral gray `#6b6a67` |
| Borders | `#e8e6e1` |
| Hover | `#eeece7` |
| Accent | muted warm clay `#c96442` |
| Success / warning / error | soft green `#3f7d58` / amber `#b07d3a` / red `#b4453a` |

- Typography: Inter (UI), JetBrains Mono (code). Comfortable 1.6–1.7 line height,
  restrained headings, max message width ≈ 68ch.
- No gradients, no strong shadows, no neon, no oversized cards, no dashboard
  widgets.
- Motion only for state (spinner, caret); respects `prefers-reduced-motion`.

---

## 4. Layout

Persistent sidebar ≥1024px, collapsible 768–1024px, drawer <768px. The sidebar
holds branding, New chat, search, recent conversations (with a context menu for
rename/delete), Documents, Approvals, Settings, and the account menu. No top
navigation bar over the conversation; the conversation gets the visual priority.

---

## 5. Tool execution experience (first-class)

An inline activity block inside the assistant turn — never a generic spinner.

```text
Let me check that for you.

┌──────────────────────────────────────────┐
│ ⚙  Searching documents                   │
│    Query: onboarding       ◉ Running · 00:04 │
└──────────────────────────────────────────┘

✓ Searching documents                      Completed · 00:06

Here is what I found…
```

States and their real triggers:

| State | Trigger |
| --- | --- |
| pending | `tool_start` received, first tick not yet elapsed |
| running | `tool_start` received → spinner + live elapsed |
| completed | `tool_end` for that `tool_call_id` |
| failed | `error` event, or a `tool_end` whose result is an `Error:` string |
| cancelled | user pressed Stop while it was running |

Timer requirements (all real, none fabricated):

- Start at the actual `tool_start` arrival, tick 1s, stop at its `tool_end`.
- Completed timers keep their final duration.
- Multiple tools in one turn, sequential or parallel, each with its own timer.
- Intervals cleared on unmount and on turn end.

Each block expands to show tool, argument summary, start time, duration, result
summary (truncated), and error text — with secrets/paths never rendered.

---

## 6. Technology stack

Next.js 16 (App Router), React 19, TypeScript, Tailwind v4, Radix primitives in
the shadcn style, lucide-react, TanStack Query 5, Zustand 5, Zod 4,
react-markdown + remark-gfm, react-syntax-highlighter, Vitest + Testing Library,
pnpm. No Streamdown (our SSE already streams; a second markdown engine would be
an unnecessary dependency).

---

## 7. Architecture

```
src/
├── app/
│   ├── (auth)/login/
│   ├── (dashboard)/{chat, chat/[threadId], documents, approvals, settings}
│   ├── api/auth/{login,logout,session}   BFF session routes
│   ├── api/backend/[...path]             authenticated streaming proxy
│   └── globals.css                       white-first design tokens
├── components/{ui,layout,shared}
├── features/{auth,chat,threads,approvals,documents}
├── lib/{api,auth,utils}
├── stores/ui.ts
└── types/api.ts
```

Auth: the FastAPI JWT never reaches JavaScript. `/api/auth/login` exchanges the
API key server-side and stores the token in an **HttpOnly** cookie;
`/api/backend/*` attaches it and forwards `text/event-stream` unbuffered.
`middleware.ts` redirects unauthenticated requests (UX gate only — the backend
re-validates everything).

---

## 8. Sprint breakdown (dependency order)

| Sprint | Scope | Depends on |
| --- | --- | --- |
| F1 | **White design system** + Claude-inspired shell, sidebar, typography | — |
| F2 | **Tool lifecycle correlation** (`tool_call_id`) + tool timeline with real timers | F1 |
| F3 | Conversation surface: welcome screen, messages, composer, streaming markdown | F1–F2 |
| F4 | Approvals in the conversation (minimal styling) | F3 |
| F5 | Documents in the same visual language | F1 |
| F6 | Responsive polish, tests, verification | F1–F5 |

Order note: F2 precedes F3 because the conversation surface renders tool
activity; building the messages first would mean rewriting them.

---

## 9. Acceptance criteria

- White background throughout the primary interface; dark is optional only.
- Sidebar minimal, compact, warm-gray, with conversation context menus.
- Composer: large, white, thin border, rounded, auto-resizing, Enter/Shift+Enter,
  Stop while streaming.
- Assistant responses render markdown, tables, lists, highlighted code with copy.
- Tool activity appears **inside** the conversation with real elapsed timers,
  multiple and parallel calls, and expansion for safe details.
- No fabricated tool activity, reasoning, or stats.
- Approvals fit naturally in the conversation; the backend validates decisions.
- Documents share the same language.
- Desktop/tablet/mobile work.
- Lint, typecheck, unit tests, production build; backend suite unregressed.

---

## 10. Known limitations

- No per-tool failure event: a raising tool is reported as a turn error.
- Cancellation is turn-level, so running tools are marked Cancelled by the client.
- Cookies carry the JWT; no server-side revocation list.
- One backend worker: two tabs on one conversation can hit `THREAD_BUSY`.
- `respond` decisions return `422`; the UI offers approve/edit/reject only.
- Windows/Node 26: `tsc` intermittently segfaults (`0xC0000005`), which Next
  reports as "Failed to type check." `typescript.ignoreBuildErrors` is `true` so
  builds are reproducible; **CI must run `pnpm typecheck`** as the real gate.

---

## 11. Progress

| Sprint | Status | Notes |
| --- | --- | --- |
| F1 | done | White-first Claude-inspired design system (`#fff` canvas, `#f7f6f3` sidebar, `#c96442` clay accent), restrained typography, quiet nav, compact conversation rows with hover menus, minimal dialogs, light-first theme provider. |
| F2 | done | Backend: additive `TurnEvent.call_id` → `tool_call_id` on `tool_start`/`tool_end` (the only reliable way to pair parallel same-name calls). UI: inline tool timeline keyed by that id, real elapsed timers (start at `tool_start`, tick 1s, freeze at `tool_end`), pending/running/completed/failed/cancelled, expandable safe details. |
| F3 | done | Welcome screen, composer (thin border, auto-resize, Enter/Shift+Enter, Stop), plain-typography assistant markdown with GFM + highlighted code + copy, progressive streaming, error/empty states. |
| F4 | done | Approval prompt inline in the conversation, subdued amber surface, approve/edit/reject with typed field editing. |
| F5 | done | Documents in the same language: dashed drop area, quiet list, hover delete with confirmation; toasts. |
| F6 | done | Settings, lint clean, 45 tests, typecheck, production build, backend suite, live verification. |

Verification log:

| Check | Result |
| --- | --- |
| `pnpm lint` | 0 errors, 0 warnings |
| `pnpm test` | 6 files, **45 tests** pass (incl. a real ticking-clock test with fake timers) |
| `pnpm typecheck` | clean (retried past the known `tsc` crash) |
| `pnpm build` | exit 0, `BUILD_ID` written |
| Backend `uv run pytest` | **690 passed** (+1 for the correlation test) |
| White theme, served CSS | `--background: #fff` first, sidebar `#f7f6f3`, accent `#c96442`; `<html>` has **no** `.dark` class |
| **Live tool events** | 3 tool calls in one turn (including **2 parallel `get_current_time`**), every one carrying a unique id, all ids paired start→end |
| Live via Next BFF | 21 frames, `tool_start`/`tool_end` present through the proxy |

Bugs found and fixed during verification:

1. **Parallel same-name tool calls were un-pairable** — the contract had no
   correlation id. Added `call_id` end to end; proven live with two concurrent
   `get_current_time` calls.
2. **Component tests could not run** — an ambient `NODE_ENV=production` meant
   React shipped its production build (no `React.act`). Pinned `NODE_ENV=test`
   for Vitest and added `@testing-library/jest-dom` setup.
3. **Composer mirrored its draft in state** — an effect-driven `setState` that
   lint flagged and that could clobber typing. Now fully controlled by the
   conversation view.
