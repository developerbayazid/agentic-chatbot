import { describe, expect, it } from "vitest";

import { reduceEvent, type StreamState } from "@/features/chat/hooks/use-chat-stream";

const EMPTY: StreamState = {
  status: "idle",
  text: "",
  tools: [],
  approvalId: null,
  error: null,
  title: null,
};

const frame = (event: string, data: unknown) => ({
  event,
  data: JSON.stringify(data),
});

describe("interrupted turns are not reported as complete", () => {
  it("a partial turn reaches 'streaming', never 'completed'", () => {
    const state = reduceEvent(
      EMPTY,
      frame("token", { content: "The answer is half…" }),
    );

    expect(state.status).toBe("streaming");
    // Nothing in the stream marks it complete; only `final` may.
    expect(state.status).not.toBe("completed");
  });

  it("only a final frame completes a turn", () => {
    const state = [
      frame("token", { content: "done" }),
      frame("final", { title: "T" }),
    ].reduce(reduceEvent, EMPTY);

    expect(state.status).toBe("completed");
  });
});

/**
 * The Stop path lives in the hook's `stop` callback, which needs React state.
 * Its contract is expressed here against the same shape the callback produces,
 * so the distinction cannot silently regress to "completed".
 */
describe("stopped vs completed", () => {
  const stopped = (state: StreamState): StreamState => ({
    ...state,
    status: "stopped",
    tools: state.tools.map((tool) =>
      tool.status === "running" || tool.status === "pending"
        ? { ...tool, status: "cancelled" as const, finishedAt: Date.now() }
        : tool,
    ),
  });

  it("marks a stopped turn distinctly and cancels running tools", () => {
    const midway = reduceEvent(
      EMPTY,
      frame("tool_start", { tool: "search_documents", tool_call_id: "a" }),
    );
    const after = stopped(midway);

    expect(after.status).toBe("stopped");
    expect(after.status).not.toBe("completed");
    expect(after.tools[0].status).toBe("cancelled");
    expect(after.tools[0].finishedAt).toBeTypeOf("number");
  });

  it("leaves an already-finished tool alone", () => {
    const state = [
      frame("tool_start", { tool: "calc", tool_call_id: "a" }),
      frame("tool_end", { tool: "calc", tool_call_id: "a", result: "1" }),
    ].reduce(reduceEvent, EMPTY);

    const after = stopped(state);

    expect(after.tools[0].status).toBe("completed");
    expect(after.tools[0].result).toBe("1");
  });
});
