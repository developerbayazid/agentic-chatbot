import { describe, expect, it } from "vitest";

import {
  describeTool,
  formatDuration,
  summariseArguments,
} from "@/features/chat/components/tool-activity";
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

describe("formatDuration", () => {
  it("renders mm:ss", () => {
    expect(formatDuration(0)).toBe("00:00");
    expect(formatDuration(3_400)).toBe("00:03");
    expect(formatDuration(65_000)).toBe("01:05");
  });

  it("never renders a negative clock", () => {
    expect(formatDuration(-500)).toBe("00:00");
  });
});

describe("describeTool / summariseArguments", () => {
  it("humanises the tool name", () => {
    expect(describeTool("search_documents")).toBe("Search documents");
    expect(describeTool("calculator")).toBe("Calculator");
  });

  it("summarises safe arguments without dumping secrets", () => {
    expect(summariseArguments(undefined)).toBeUndefined();
    expect(summariseArguments({ query: "onboarding" })).toBe("query: onboarding");
    expect(
      summariseArguments({ a: 1, b: 2, c: 3, d: 4 }),
    ).not.toContain("d:");
  });
});

describe("tool timers from real events", () => {
  it("opens an activity at tool_start and closes it at tool_end", () => {
    let state = reduceEvent(
      EMPTY,
      frame("tool_start", {
        tool: "search_documents",
        arguments: { query: "x" },
        tool_call_id: "call_1",
      }),
    );

    const opened = state.tools[0];
    expect(opened.status).toBe("running");
    expect(opened.startedAt).toBeTypeOf("number");
    expect(opened.finishedAt).toBeUndefined();

    state = reduceEvent(
      state,
      frame("tool_end", {
        tool: "search_documents",
        result: '{"count":2}',
        tool_call_id: "call_1",
      }),
    );

    const settled = state.tools[0];
    expect(settled.status).toBe("completed");
    expect(settled.finishedAt).toBeGreaterThanOrEqual(settled.startedAt!);
  });

  it("pairs parallel calls to the SAME tool by id, not by name", () => {
    let state = reduceEvent(
      EMPTY,
      frame("tool_start", { tool: "search_documents", tool_call_id: "call_1" }),
    );
    state = reduceEvent(
      state,
      frame("tool_start", { tool: "search_documents", tool_call_id: "call_2" }),
    );

    expect(state.tools).toHaveLength(2);

    // Results arrive out of order; each must settle its own row.
    state = reduceEvent(
      state,
      frame("tool_end", {
        tool: "search_documents",
        result: "second",
        tool_call_id: "call_2",
      }),
    );

    expect(state.tools[0].status).toBe("running");
    expect(state.tools[0].callId).toBe("call_1");
    expect(state.tools[1].status).toBe("completed");
    expect(state.tools[1].result).toBe("second");

    state = reduceEvent(
      state,
      frame("tool_end", {
        tool: "search_documents",
        result: "first",
        tool_call_id: "call_1",
      }),
    );

    expect(state.tools[0].status).toBe("completed");
    expect(state.tools[0].result).toBe("first");
    // The early completion kept its own timestamp.
    expect(state.tools[1].finishedAt).toBeDefined();
  });

  it("keeps a completed timer while another tool starts", () => {
    let state = reduceEvent(
      EMPTY,
      frame("tool_start", { tool: "a", tool_call_id: "1" }),
    );
    state = reduceEvent(
      state,
      frame("tool_end", { tool: "a", result: "ok", tool_call_id: "1" }),
    );
    const done = { ...state.tools[0] };

    state = reduceEvent(state, frame("tool_start", { tool: "b", tool_call_id: "2" }));

    expect(state.tools[0].finishedAt).toBe(done.finishedAt);
    expect(state.tools[0].status).toBe("completed");
    expect(state.tools[1].status).toBe("running");
  });

  it("marks an Error: result as failed", () => {
    let state = reduceEvent(EMPTY, frame("tool_start", { tool: "x", tool_call_id: "1" }));
    state = reduceEvent(
      state,
      frame("tool_end", { tool: "x", result: "Error: no such product", tool_call_id: "1" }),
    );

    expect(state.tools[0].status).toBe("failed");
    expect(state.tools[0].result).toContain("no such product");
  });

  it("fails every running tool when the stream errors", () => {
    let state = reduceEvent(EMPTY, frame("tool_start", { tool: "x", tool_call_id: "1" }));
    state = reduceEvent(
      state,
      frame("error", { code: "STREAM_ERROR", message: "The response failed." }),
    );

    expect(state.status).toBe("error");
    expect(state.tools[0].status).toBe("failed");
    expect(state.tools[0].error).toBe("The response failed.");
  });

  it("falls back to a stable key when the backend sends no id", () => {
    const state = reduceEvent(EMPTY, frame("tool_start", { tool: "calculator" }));

    expect(state.tools[0].callId).toBe("calculator#0");
    expect(state.tools[0].status).toBe("running");
  });
});
