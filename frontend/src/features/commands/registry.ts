/**
 * Slash-command registry.
 *
 * Mirrors the CLI's `COMMANDS` (13 commands, see `COMMAND-PARITY.md`) and adds
 * the planned namespaces so the composer already understands them.
 *
 * Hard rules, enforced by `commands.test.ts`:
 *  1. an `available` command must have a handler;
 *  2. a `planned` command must NOT have a handler and MUST have a message;
 *  3. nothing here executes a shell command — handlers only touch existing
 *     services through `lib/api` or navigate.
 */

export type Availability = "available" | "planned";

export type CommandCategory = "conversation" | "workspace" | "future";

export interface CommandContext {
  /** Current conversation, when one is open. */
  threadId: string | null;
}

export interface CommandDefinition {
  name: string;
  aliases: string[];
  description: string;
  category: CommandCategory;
  availability: Availability;
  /** Shown when the command needs an argument it did not receive. */
  usage?: string;
  /** Only present for `available` commands. */
  handler?: (context: CommandContext) => void | Promise<void>;
  /** Only present for `planned` commands; shown instead of doing anything. */
  comingSoonMessage?: string;
}

export const CATEGORY_LABELS: Record<CommandCategory, string> = {
  conversation: "Conversation",
  workspace: "Workspace",
  future: "Coming soon",
};

const FUTURE_TEMPLATE = (label: string, detail: string) =>
  `${label} are coming soon. ${detail} This feature will be available in a future update.`;

/* ------------------------------------------------------------------ planned -- */

function planned(
  name: string,
  description: string,
  message: string,
  aliases: string[] = [],
): CommandDefinition {
  return {
    name,
    aliases,
    description,
    category: "future",
    availability: "planned",
    comingSoonMessage: message,
  };
}

const PLANNED: CommandDefinition[] = [
  planned(
    "/skills",
    "Manage reusable agent skills",
    FUTURE_TEMPLATE("Skills", "Reusable agent skills will be installable and activatable."),
    ["/skill"],
  ),
  planned(
    "/plugins",
    "Manage installed plugins",
    FUTURE_TEMPLATE("Plugins", "Plugins will add tools and integrations."),
    ["/plugin"],
  ),
  planned(
    "/mcp",
    "Manage MCP servers",
    FUTURE_TEMPLATE("MCP servers", "External tool servers will be connectable."),
  ),
  planned(
    "/memory",
    "Inspect or clear assistant memory",
    FUTURE_TEMPLATE("Memory management", "Long-term memory will be inspectable."),
  ),
  planned(
    "/model",
    "Choose the language model",
    FUTURE_TEMPLATE("Model selection", "The model will be switchable per conversation."),
  ),
];

/* ------------------------------------------------------------------ builder -- */

/**
 * `buildCommands` takes the web actions as arguments rather than importing
 * routers, which keeps the registry pure and lets tests exercise every entry
 * without a running application.
 */
export function buildCommands(actions: {
  newChat: (context: CommandContext) => void | Promise<void>;
  openThreads: (context: CommandContext) => void | Promise<void>;
  showHistory: (context: CommandContext) => void | Promise<void>;
  renameThread: (context: CommandContext) => void | Promise<void>;
  deleteThread: (context: CommandContext) => void | Promise<void>;
  openApprovals: (context: CommandContext) => void | Promise<void>;
  openDocuments: (context: CommandContext) => void | Promise<void>;
  showHelp: (context: CommandContext) => void | Promise<void>;
}): CommandDefinition[] {
  return [
    {
      name: "/new",
      aliases: ["/clear-history"],
      description: "Start a new conversation",
      category: "conversation",
      availability: "available",
      handler: actions.newChat,
    },
    {
      name: "/threads",
      aliases: [],
      description: "Browse your conversations",
      category: "conversation",
      availability: "available",
      handler: actions.openThreads,
    },
    {
      name: "/history",
      aliases: [],
      description: "Show this conversation's messages",
      category: "conversation",
      availability: "available",
      handler: actions.showHistory,
    },
    {
      name: "/rename",
      aliases: [],
      description: "Rename the current conversation",
      category: "conversation",
      availability: "available",
      usage: "/rename <title>",
      handler: actions.renameThread,
    },
    {
      name: "/delete",
      aliases: [],
      description: "Delete the current conversation",
      category: "conversation",
      availability: "available",
      usage: "/delete",
      handler: actions.deleteThread,
    },
    {
      name: "/approvals",
      aliases: [],
      description: "Review actions waiting for your approval",
      category: "workspace",
      availability: "available",
      handler: actions.openApprovals,
    },
    {
      name: "/documents",
      aliases: ["/ingest"],
      description: "Upload and manage indexed documents",
      category: "workspace",
      availability: "available",
      handler: actions.openDocuments,
    },
    {
      name: "/help",
      aliases: [],
      description: "List available commands",
      category: "workspace",
      availability: "available",
      handler: actions.showHelp,
    },
    ...PLANNED,
  ];
}

/** Normalise `help` or `/HELP` to `/help`. */
export function normalizeCommand(input: string): string {
  const trimmed = input.trim().toLowerCase();

  if (!trimmed) return "";

  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

/** Find a command by name or alias. */
export function resolveCommand(
  commands: CommandDefinition[],
  input: string,
): CommandDefinition | null {
  const target = normalizeCommand(input);

  return (
    commands.find(
      (command) => command.name === target || command.aliases.includes(target),
    ) ?? null
  );
}

/**
 * Filter for the composer menu.
 *
 * Prefix matches on the name or an alias rank above substring matches on the
 * description, so typing `/m` surfaces `/mcp` and `/model` before anything that
 * merely mentions "manage".
 */
export function filterCommands(
  commands: CommandDefinition[],
  query: string,
): CommandDefinition[] {
  const needle = normalizeCommand(query).replace(/^\//, "");

  if (!needle) return commands;

  const prefix: CommandDefinition[] = [];
  const contains: CommandDefinition[] = [];

  for (const command of commands) {
    const names = [command.name, ...command.aliases].map((value) =>
      value.replace(/^\//, ""),
    );

    if (names.some((value) => value.startsWith(needle))) {
      prefix.push(command);
    } else if (
      names.some((value) => value.includes(needle)) ||
      command.description.toLowerCase().includes(needle)
    ) {
      contains.push(command);
    }
  }

  return [...prefix, ...contains];
}

/** Split `/rename My new title` into `{ command: "/rename", argument: "My new title" }`. */
export function splitCommand(text: string): {
  command: string;
  argument: string;
} {
  const trimmed = text.trim();
  const space = trimmed.indexOf(" ");

  if (space === -1) {
    return { command: normalizeCommand(trimmed), argument: "" };
  }

  return {
    command: normalizeCommand(trimmed.slice(0, space)),
    argument: trimmed.slice(space + 1).trim(),
  };
}
