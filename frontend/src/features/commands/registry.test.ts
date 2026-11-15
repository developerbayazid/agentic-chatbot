import { describe, expect, it, vi } from "vitest";

import {
  buildCommands,
  filterCommands,
  normalizeCommand,
  resolveCommand,
  splitCommand,
  type CommandDefinition,
} from "@/features/commands/registry";

function makeActions() {
  return {
    newChat: vi.fn(),
    openThreads: vi.fn(),
    showHistory: vi.fn(),
    renameThread: vi.fn(),
    deleteThread: vi.fn(),
    openApprovals: vi.fn(),
    openDocuments: vi.fn(),
    showHelp: vi.fn(),
  };
}

const commands = buildCommands(makeActions());

describe("registry invariants", () => {
  it("gives every available command a handler", () => {
    for (const command of commands.filter((c) => c.availability === "available")) {
      expect(command.handler, `${command.name} needs a handler`).toBeTypeOf("function");
    }
  });

  it("never gives a planned command a handler, and always explains why", () => {
    const planned = commands.filter((c) => c.availability === "planned");

    expect(planned.length).toBeGreaterThan(0);

    for (const command of planned) {
      expect(command.handler, `${command.name} must not execute`).toBeUndefined();
      expect(command.comingSoonMessage, `${command.name} needs a message`).toBeTruthy();
      expect(command.comingSoonMessage).toMatch(/coming soon/i);
    }
  });

  it("has no duplicate names or aliases", () => {
    const seen = new Map<string, string>();

    for (const command of commands) {
      for (const token of [command.name, ...command.aliases]) {
        expect(seen.has(token), `${token} declared twice`).toBe(false);
        seen.set(token, command.name);
      }
    }
  });

  it("covers the real CLI commands that have a web meaning", () => {
    const names = commands.map((c) => c.name);

    for (const expected of [
      "/new",
      "/threads",
      "/history",
      "/rename",
      "/delete",
      "/approvals",
      "/documents",
      "/help",
    ]) {
      expect(names).toContain(expected);
    }
  });

  it("excludes terminal-only commands rather than faking them", () => {
    const names = commands.map((c) => c.name);

    // `/exit` would end a process; `/clear` only clears a terminal viewport.
    expect(names).not.toContain("/exit");
    expect(names).not.toContain("/clear");
  });

  it("does not invent /switch, which the CLI does not have", () => {
    expect(commands.map((c) => c.name)).not.toContain("/switch");
  });

  it("registers the future namespaces as planned", () => {
    const planned = commands
      .filter((c) => c.availability === "planned")
      .map((c) => c.name);

    expect(planned).toEqual(
      expect.arrayContaining(["/skills", "/plugins", "/mcp", "/memory", "/model"]),
    );
  });
});

describe("normalizeCommand", () => {
  it("accepts a bare name or a slash name", () => {
    expect(normalizeCommand("help")).toBe("/help");
    expect(normalizeCommand("/help")).toBe("/help");
    expect(normalizeCommand("  /HELP ")).toBe("/help");
    expect(normalizeCommand("")).toBe("");
  });
});

describe("resolveCommand", () => {
  it("resolves by name and by alias", () => {
    expect(resolveCommand(commands, "/new")?.name).toBe("/new");
    expect(resolveCommand(commands, "new")?.name).toBe("/new");
    expect(resolveCommand(commands, "/ingest")?.name).toBe("/documents");
  });

  it("returns null for an unknown command", () => {
    expect(resolveCommand(commands, "/nope")).toBeNull();
  });
});

describe("filterCommands", () => {
  it("returns everything for an empty query", () => {
    expect(filterCommands(commands, "/")).toHaveLength(commands.length);
  });

  it("ranks prefix matches above description matches", () => {
    const result = filterCommands(commands, "/m");
    const names = result.map((c) => c.name);

    // /mcp and /model and /memory start with "m".
    expect(names.slice(0, 3).every((name) => name.startsWith("/m"))).toBe(true);
  });

  it("matches aliases", () => {
    const result = filterCommands(commands, "/ingest");

    expect(result.map((c) => c.name)).toContain("/documents");
  });

  it("can match on the description", () => {
    const result = filterCommands(commands, "approval");

    expect(result.map((c) => c.name)).toContain("/approvals");
  });

  it("returns nothing when nothing matches", () => {
    expect(filterCommands(commands, "/zzzz")).toEqual([]);
  });
});

describe("splitCommand", () => {
  it("separates the command from its argument", () => {
    expect(splitCommand("/rename My new title")).toEqual({
      command: "/rename",
      argument: "My new title",
    });
  });

  it("handles a command with no argument", () => {
    expect(splitCommand("/new")).toEqual({ command: "/new", argument: "" });
  });

  it("normalises the command part only", () => {
    expect(splitCommand("  RENAME  Keep Case ")).toEqual({
      command: "/rename",
      argument: "Keep Case",
    });
  });
});

describe("handlers are the only path to an action", () => {
  it("a planned command cannot be executed even if its handler is invoked", () => {
    const planned = commands.find((c): c is CommandDefinition => c.name === "/skills");

    expect(planned).toBeDefined();
    // There is no function to call — the UI must show the message instead.
    expect("handler" in (planned as object)).toBe(false);
  });
});
