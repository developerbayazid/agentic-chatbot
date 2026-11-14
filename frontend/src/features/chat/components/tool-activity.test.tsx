import { afterEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";

import { ToolActivityRow } from "@/features/chat/components/tool-activity";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("ToolActivityRow", () => {
  it("shows a running tool with a live elapsed clock", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));

    const startedAt = Date.now();

    render(
      <ToolActivityRow
        activity={{
          callId: "call_1",
          name: "search_documents",
          status: "running",
          startedAt,
          arguments: { query: "onboarding" },
        }}
      />,
    );

    expect(screen.getByText("Search documents")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByLabelText("elapsed time")).toHaveTextContent("00:00");

    // Two real seconds later the clock has ticked from the recorded start.
    act(() => {
      vi.advanceTimersByTime(2_000);
    });

    expect(screen.getByLabelText("elapsed time")).toHaveTextContent("00:02");
  });

  it("freezes the duration once the tool completes", () => {
    const startedAt = Date.now();

    render(
      <ToolActivityRow
        activity={{
          callId: "call_1",
          name: "search_documents",
          status: "completed",
          startedAt,
          finishedAt: startedAt + 6_000,
          result: '{"count":2}',
        }}
      />,
    );

    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByLabelText("elapsed time")).toHaveTextContent("00:06");
  });

  it("renders a failed tool with its error", () => {
    const startedAt = Date.now();

    render(
      <ToolActivityRow
        activity={{
          callId: "call_1",
          name: "update_product",
          status: "failed",
          startedAt,
          finishedAt: startedAt + 1_000,
          error: "The response failed.",
        }}
      />,
    );

    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders a cancelled tool", () => {
    render(
      <ToolActivityRow
        activity={{
          callId: "call_1",
          name: "search_documents",
          status: "cancelled",
          startedAt: Date.now(),
          finishedAt: Date.now() + 2_000,
        }}
      />,
    );

    expect(screen.getByText("Cancelled")).toBeInTheDocument();
  });

  it("expands to show safe execution details", () => {
    const startedAt = Date.now();

    render(
      <ToolActivityRow
        activity={{
          callId: "call_1",
          name: "search_documents",
          status: "completed",
          startedAt,
          finishedAt: startedAt + 3_000,
          arguments: { query: "onboarding" },
          result: '{"count":2}',
        }}
      />,
    );

    act(() => {
      screen.getByRole("button", { expanded: false }).click();
    });

    expect(screen.getByRole("button", { expanded: true })).toBeInTheDocument();
    expect(screen.getByText("Tool")).toBeInTheDocument();
    expect(screen.getByText("Duration")).toBeInTheDocument();
    expect(screen.getByText("Arguments")).toBeInTheDocument();
    expect(screen.getByText("Result")).toBeInTheDocument();
  });
});
