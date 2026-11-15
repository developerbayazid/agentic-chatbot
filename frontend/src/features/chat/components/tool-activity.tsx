"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, Check, ChevronRight, Loader2, Slash } from "lucide-react";

import { cn } from "@/lib/utils/cn";

export type ToolStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface ToolActivity {
  /** Backend `tool_call_id` — the correlation key, not the tool name. */
  callId: string;
  name: string;
  /** Parsed arguments, when the backend sent a JSON object. */
  arguments?: unknown;
  status: ToolStatus;
  /** Epoch ms of the real `tool_start` arrival. */
  startedAt?: number;
  /** Epoch ms of the real `tool_end` arrival. */
  finishedAt?: number;
  /** Tool output, as returned by the backend. */
  result?: string;
  /** Stream-level error that stopped the turn. */
  error?: string;
}

/** Human-readable label for a tool name: `search_documents` → `Searching documents`. */
export function describeTool(name: string): string {
  const words = name.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;

  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/**
 * A single tool execution.
 *
 * The elapsed time is measured from the real `tool_start` event to the real
 * `tool_end` event. Nothing here runs on a timer of its own: while running, one
 * interval re-renders the clock; on completion the final duration is frozen.
 */
export function ToolActivityRow({ activity }: { activity: ToolActivity }) {
  const [now, setNow] = useState(() => Date.now());
  const [expanded, setExpanded] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const running = activity.status === "running" || activity.status === "pending";

  useEffect(() => {
    if (!running) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }

      return;
    }

    intervalRef.current = setInterval(() => setNow(Date.now()), 1000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [running]);

  const elapsed =
    activity.startedAt === undefined
      ? undefined
      : (activity.finishedAt ?? now) - activity.startedAt;

  const detail = summariseArguments(activity.arguments);

  return (
    <div
      className={cn(
        "not-prose rounded-xl border border-border bg-surface px-3 py-2.5",
        "text-[13px] transition-colors",
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded((open) => !open)}
        aria-expanded={expanded}
        className="flex w-full items-start gap-2 text-left"
      >
        <span className="mt-0.5 shrink-0" aria-hidden>
          <StatusIcon status={activity.status} />
        </span>

        <span className="min-w-0 flex-1">
          <span className="block font-medium text-foreground">
            {describeTool(activity.name)}
          </span>
          {detail && (
            <span className="mt-0.5 block truncate font-mono text-[11.5px] text-muted">
              {detail}
            </span>
          )}
          <span className="mt-0.5 flex items-center gap-1.5 text-[11.5px] text-muted">
            <StatusLabel status={activity.status} />
            {elapsed !== undefined && (
              <>
                <span aria-hidden>·</span>
                <span className="tabular-nums" aria-label="elapsed time">
                  {formatDuration(elapsed)}
                </span>
              </>
            )}
          </span>
        </span>

        <ChevronRight
          className={cn(
            "mt-1 size-3.5 shrink-0 text-muted transition-transform",
            expanded && "rotate-90",
          )}
          aria-hidden
        />
      </button>

      {expanded && (
        <dl className="mt-2.5 space-y-1.5 border-t border-border pt-2.5 text-[12px]">
          <Detail label="Tool" value={activity.name} mono />
          {activity.startedAt !== undefined && (
            <Detail
              label="Started"
              value={new Date(activity.startedAt).toLocaleTimeString()}
            />
          )}
          {elapsed !== undefined && (
            <Detail label="Duration" value={formatDuration(elapsed)} mono />
          )}
          {activity.arguments !== undefined && (
            <Detail label="Arguments" value={safeJson(activity.arguments)} mono />
          )}
          {activity.result !== undefined && (
            <Detail label="Result" value={truncate(activity.result, 400)} mono />
          )}
          {activity.error && <Detail label="Error" value={activity.error} />}
        </dl>
      )}
    </div>
  );
}

function StatusIcon({ status }: { status: ToolStatus }) {
  switch (status) {
    case "running":
    case "pending":
      return <Loader2 className="size-3.5 animate-spin text-accent" />;
    case "completed":
      return <Check className="size-3.5 text-success" />;
    case "failed":
      return <AlertCircle className="size-3.5 text-danger" />;
    case "cancelled":
      return <Slash className="size-3.5 text-muted" />;
  }
}

function StatusLabel({ status }: { status: ToolStatus }) {
  switch (status) {
    case "pending":
      return <span>Queued</span>;
    case "running":
      return <span>Running</span>;
    case "completed":
      return <span className="text-success">Completed</span>;
    case "failed":
      return <span className="text-danger">Failed</span>;
    case "cancelled":
      return <span>Cancelled</span>;
  }
}

function Detail({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex gap-2">
      <dt className="w-20 shrink-0 text-muted">{label}</dt>
      <dd
        className={cn(
          "min-w-0 flex-1 break-words text-foreground",
          mono && "font-mono text-[11.5px]",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

/** A short, safe summary of the arguments (never a secret or a path). */
export function summariseArguments(args: unknown): string | undefined {
  if (args === undefined || args === null) {
    return undefined;
  }

  if (typeof args === "string") {
    return truncate(args, 80);
  }

  if (typeof args !== "object") {
    return String(args);
  }

  const entries = Object.entries(args as Record<string, unknown>).slice(0, 3);

  if (entries.length === 0) {
    return undefined;
  }

  return entries
    .map(([key, value]) => `${key}: ${truncate(stringify(value), 40)}`)
    .join("  ·  ");
}

function stringify(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function safeJson(value: unknown): string {
  try {
    return truncate(JSON.stringify(value), 400);
  } catch {
    return String(value);
  }
}

function truncate(text: string, limit: number): string {
  const single = text.replace(/\s+/g, " ").trim();
  return single.length > limit ? `${single.slice(0, limit)}…` : single;
}
