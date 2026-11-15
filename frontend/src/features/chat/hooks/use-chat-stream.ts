"use client";

import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { errorMessage, isAbortError } from "@/lib/api/errors";
import { requestStream } from "@/lib/api/client";
import { parseData, SseParser, type SseEvent } from "@/lib/api/sse";
import { threadKeys } from "@/features/threads/hooks/use-threads";
import type {
  SseApprovalFrame,
  SseErrorFrame,
  SseFinalFrame,
  SseThreadFrame,
  SseTokenFrame,
  SseToolEndFrame,
  SseToolStartFrame,
} from "@/types/api";
import type { ToolActivity } from "@/features/chat/components/tool-activity";

export interface StreamState {
  /**
   * `stopped` is distinct from `completed` on purpose: a turn the reader
   * interrupted must not present itself as a finished answer.
   */
  status: "idle" | "streaming" | "awaiting_approval" | "completed" | "stopped" | "error";
  text: string;
  /** Keyed by `tool_call_id`, in first-seen order via the `order` array. */
  tools: ToolActivity[];
  approvalId: string | null;
  error: string | null;
  title: string | null;
}

const INITIAL: StreamState = {
  status: "idle",
  text: "",
  tools: [],
  approvalId: null,
  error: null,
  title: null,
};

/** Fallback key when a frame has no id (older backend or a hand-written frame). */
function keyFor(callId: string | null | undefined, name: string, index: number) {
  return callId ?? `${name}#${index}`;
}

/**
 * Fold one SSE frame into the turn state.
 *
 * Every field is driven by a real backend event:
 *  - `token` appends text,
 *  - `tool_start` opens an activity stamped with the arrival time,
 *  - `tool_end` closes the activity with the same `tool_call_id` and stamps the
 *    finish time, which is what makes the displayed duration genuine,
 *  - `approval_required` stops the turn.
 */
export function reduceEvent(state: StreamState, event: SseEvent): StreamState {
  switch (event.event) {
    case "token": {
      const frame = parseData<SseTokenFrame>(event);

      if (!frame?.content) {
        return state;
      }

      return { ...state, text: state.text + frame.content, status: "streaming" };
    }

    case "tool_start": {
      const frame = parseData<SseToolStartFrame>(event);

      if (!frame?.tool) {
        return state;
      }

      const callId = keyFor(frame.tool_call_id, frame.tool, state.tools.length);

      return {
        ...state,
        tools: [
          ...state.tools,
          {
            callId,
            name: frame.tool,
            arguments: frame.arguments,
            status: "running",
            startedAt: Date.now(),
          },
        ],
      };
    }

    case "tool_end": {
      const frame = parseData<SseToolEndFrame>(event);

      if (!frame?.tool) {
        return state;
      }

      const result =
        typeof frame.result === "string"
          ? frame.result
          : frame.result === undefined
            ? undefined
            : JSON.stringify(frame.result);

      // Prefer the id; fall back to the first still-running call of that name.
      const matches = (tool: ToolActivity) =>
        frame.tool_call_id
          ? tool.callId === frame.tool_call_id
          : tool.name === frame.tool && tool.status === "running";

      let settled = false;
      const tools = state.tools.map((tool) => {
        if (!settled && matches(tool)) {
          settled = true;

          return {
            ...tool,
            status: isErrorResult(result) ? ("failed" as const) : ("completed" as const),
            result,
            finishedAt: Date.now(),
          };
        }

        return tool;
      });

      return { ...state, tools };
    }

    case "approval_required": {
      const frame = parseData<SseApprovalFrame>(event);

      return {
        ...state,
        status: "awaiting_approval",
        approvalId: frame?.approval_id ?? null,
      };
    }

    case "final": {
      const frame = parseData<SseFinalFrame>(event);

      return { ...state, status: "completed", title: frame?.title ?? null };
    }

    case "error": {
      const frame = parseData<SseErrorFrame>(event);
      const message = frame?.message ?? "The response failed.";

      // Close anything still running: the turn has stopped.
      return {
        ...state,
        status: "error",
        error: message,
        tools: state.tools.map((tool) =>
          tool.status === "running" || tool.status === "pending"
            ? { ...tool, status: "failed", error: message, finishedAt: Date.now() }
            : tool,
        ),
      };
    }

    default:
      return state;
  }
}

function isErrorResult(result: string | undefined): boolean {
  return typeof result === "string" && result.trimStart().startsWith("Error:");
}

/** Extract the thread id from the opening `thread` frame. */
function threadFrom(event: SseEvent): string | null {
  if (event.event !== "thread") {
    return null;
  }

  return parseData<SseThreadFrame>(event)?.thread_id ?? null;
}

/**
 * One streaming turn over `POST /api/v1/chat/stream`.
 *
 * Aborting the request is a genuine Stop: the backend's generator sees
 * `GeneratorExit`, closes the graph stream, and releases the conversation lock.
 * Running tools are marked Cancelled because the turn, not the tool, was stopped.
 */
export function useChatStream() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<StreamState>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;

    setState((previous) =>
      previous.status === "streaming"
        ? {
            ...previous,
            // Not "completed": the answer was interrupted, and saying otherwise
            // would present a truncated reply as a finished one.
            status: "stopped",
            tools: previous.tools.map((tool) =>
              tool.status === "running" || tool.status === "pending"
                ? {
                    ...tool,
                    status: "cancelled",
                    finishedAt: Date.now(),
                  }
                : tool,
            ),
          }
        : previous,
    );
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState(INITIAL);
  }, []);

  const send = useCallback(
    async (message: string, threadId: string | null): Promise<string | null> => {
      const controller = new AbortController();
      abortRef.current = controller;

      setState({ ...INITIAL, status: "streaming" });

      let resolvedThreadId = threadId;

      try {
        const response = await requestStream("/api/v1/chat/stream", {
          json: {
            message,
            ...(threadId ? { thread_id: threadId } : {}),
          },
          signal: controller.signal,
        });

        const reader = response.body?.getReader();

        if (!reader) {
          throw new Error("The server returned an empty stream.");
        }

        const decoder = new TextDecoder();
        const parser = new SseParser();

        const consume = (events: SseEvent[]) => {
          for (const event of events) {
            resolvedThreadId = threadFrom(event) ?? resolvedThreadId;
            setState((previous) => reduceEvent(previous, event));
          }
        };

        for (;;) {
          const { value, done } = await reader.read();

          if (done) {
            break;
          }

          consume(parser.push(decoder.decode(value, { stream: true })));
        }

        consume(parser.flush());

        setState((previous) =>
          previous.status === "streaming"
            ? { ...previous, status: "completed" }
            : previous,
        );
      } catch (cause) {
        if (!isAbortError(cause)) {
          setState((previous) => ({
            ...previous,
            status: "error",
            error: errorMessage(cause),
          }));
        }
      } finally {
        abortRef.current = null;

        // Targeted invalidation: the conversation list changes (titles, recency)
        // and this one thread's stored history is now stale. Invalidating the
        // whole `["threads"]` prefix would refetch every cached conversation.
        void queryClient.invalidateQueries({ queryKey: threadKeys.list });

        if (resolvedThreadId) {
          void queryClient.invalidateQueries({
            queryKey: threadKeys.history(resolvedThreadId),
          });
        }
      }

      return resolvedThreadId;
    },
    [queryClient],
  );

  return { ...state, send, stop, reset };
}
