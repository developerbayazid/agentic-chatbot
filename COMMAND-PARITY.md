# CLI ↔ Web Command Parity

Maps every real CLI command to a web action. Derived from
`src/agentic_chatbot/cli/commands.py` — the `COMMANDS` list holds **13**
commands (verified programmatically, not counted by eye). The web never
executes a shell command or reimplements business logic; each mapped action
calls an existing FastAPI endpoint or service method.

## Supported (mapped to real web actions)

| CLI | Web action | Backend | Notes |
| --- | --- | --- | --- |
| `/help [command]` | Opens the command menu; `/help <cmd>` shows that command's details | none (client registry) | registry mirrors CLI metadata |
| `/status` | Settings → status card | `GET /health`, `GET /health/ready`, `GET /api/auth/session` | secrets never shown |
| `/version` | Settings → About | none (build info) | |
| `/ingest [path] [ns]` | Documents → upload (drag-drop or picker) | `POST /api/v1/documents` | browser cannot pass a server path; the file body is the input |
| `/documents [ns]` | Documents page | `GET /api/v1/documents` | listing only; upload lives on the same page |
| `/new` | New chat + navigate | `POST /api/v1/chat` (with no `thread_id`) | thread is created by the first message |
| `/threads` | Sidebar conversation list | `GET /api/v1/threads` | the real switcher; there is no `/switch` in the CLI |
| `/history` | Conversation view / restores messages | `GET /api/v1/threads/{id}/history` | |
| `/approvals` | Approvals page, and inline in chat | `GET /api/v1/approvals`, `GET /api/v1/approvals/{id}` | read-only list matches the CLI |
| `/rename [title]` | `/rename` → rename dialog | `PATCH /api/v1/threads/{id}` | 1–100 chars, matching the CLI truncation |
| `/delete [id]` | `/delete` → confirm dialog | `DELETE /api/v1/threads/{id}` | confirmation is mandatory in the browser |

## Not mapped (terminal-only, by design)

| CLI | Why not mapped |
| --- | --- |
| `/clear` | Clears the *terminal viewport*. A browser has no equivalent, and clearing the conversation would delete real data. |
| `/exit` | Ends the CLI process. The browser must never terminate a backend process or session; logout is a separate, explicit action. |

These two are **excluded from the web command registry** rather than shown as
disabled, because presenting them would suggest the browser could do something
it cannot.

## Commands the brief mentions that do not exist

| Command | Reality |
| --- | --- |
| `/switch` | Not implemented. Its function is covered by `/threads` (the picker). No alias will be added unless requested. |

## Planned commands (Coming Soon, no backend)

| Command | Message |
| --- | --- |
| `/skills`, `/skills list`, `/skills run` | "Skills are coming soon. Reusable agent skills will be available in a future update." |
| `/plugins`, `/plugins list` | "Plugins are coming soon. Installable extensions will be available in a future update." |
| `/mcp`, `/mcp servers`, `/mcp connect` | "MCP servers are coming soon. External tool servers will be available in a future update." |
| `/tools`, `/tools list` | Real once `GET /api/v1/tools` lands (Sprint 4); until then the same Coming Soon behaviour. |
| `/memory` | "Memory management is coming soon." |
| `/model` | "Model selection is coming soon." |

These entries exist so the composer, the sidebar, and the registry already
support them. **None of them fakes a successful execution** — each returns the
message above and performs no request.

## Registry contract (Sprint 3)

```ts
type Availability = "available" | "planned" | "disabled";

interface CommandDefinition {
  name: string;              // "/new"
  aliases?: string[];        // e.g. ["new"]
  description: string;
  category: "general" | "conversation" | "workspace" | "future";
  availability: Availability;
  requiresArgs?: boolean;
  usage?: string;
  handler?: () => void | Promise<void>;   // only for "available"
  comingSoonMessage?: string;             // only for "planned"/"disabled"
}
```

Invariants enforced by tests:

1. An `available` command **must** have a `handler`.
2. A `planned` or `disabled` command **must not** have a handler, and **must**
   have a `comingSoonMessage`.
3. No handler may touch `window.location` to an external origin, spawn a
   process, or bypass `lib/api`.
