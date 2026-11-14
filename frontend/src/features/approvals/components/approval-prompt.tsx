"use client";

import { useState } from "react";
import { AlertTriangle, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api/errors";
import { useApprovalDetail, useDecideApproval } from "@/features/approvals/hooks/use-approvals";
import type { ApprovalDetail, ApprovalSummary, Decision } from "@/types/api";

/**
 * Human-in-the-loop panel, inline in the conversation.
 *
 * The backend is the only thing that executes an approved action; this submits a
 * decision and reports what came back. It never calls a tool.
 */
export function ApprovalPrompt({
  approval,
  onDecided,
}: {
  approval: ApprovalSummary;
  onDecided: () => void;
}) {
  const detail = useApprovalDetail(approval.approval_id);
  const decide = useDecideApproval();
  const [mode, setMode] = useState<"idle" | "edit">("idle");
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const model: ApprovalDetail | ApprovalSummary = detail.data ?? approval;
  const editable = detail.data?.editable_fields ?? [];
  const fieldTypes = detail.data?.field_types ?? {};
  const args = draft ?? model.arguments;

  async function submit(decision: Decision) {
    setError(null);

    try {
      await decide.mutateAsync({
        approvalId: approval.approval_id,
        decision: {
          decision,
          comment: comment.trim() || null,
          ...(decision === "edit" ? { edited_arguments: args } : {}),
        },
      });

      onDecided();
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }

  return (
    <section
      aria-label="Approval required"
      className="rounded-xl border border-warning/30 bg-warning-soft/60 p-4"
    >
      <header className="flex items-start gap-2">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-warning" />
        <div className="min-w-0">
          <h3 className="text-[14px] font-medium">Your approval is needed</h3>
          <p className="mt-0.5 text-[12.5px] text-muted">
            {model.title}
            <span className="mx-1.5" aria-hidden>·</span>
            <span className="font-mono text-[11.5px]">{model.action}</span>
          </p>
        </div>
      </header>

      {detail.data?.details && detail.data.details.length > 0 && (
        <dl className="mt-3 space-y-1 text-[12.5px]">
          {(detail.data.details as [string, unknown][]).map(([label, value], index) => (
            <div key={index} className="flex gap-2">
              <dt className="w-40 shrink-0 text-muted">{label}</dt>
              <dd className="min-w-0 flex-1 text-foreground">{String(value)}</dd>
            </div>
          ))}
        </dl>
      )}

      {detail.data?.warnings && detail.data.warnings.length > 0 && (
        <ul className="mt-3 space-y-1 text-[12.5px] text-warning">
          {(detail.data.warnings as unknown[]).map((warning, index) => (
            <li key={index} className="flex items-start gap-1.5">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              {String(warning)}
            </li>
          ))}
        </ul>
      )}

      {mode === "edit" && (
        <div className="mt-3 space-y-2">
          {editable.map((field) => (
            <label key={field} className="block text-[12.5px]">
              <span className="text-muted">
                {field}{" "}
                <span className="font-mono text-[10.5px]">
                  ({fieldTypes[field] ?? "value"})
                </span>
              </span>
              <Input
                className="mt-1 h-8 font-mono text-[12.5px]"
                value={formatValue(args[field])}
                onChange={(event) =>
                  setDraft((previous) => ({
                    ...(previous ?? model.arguments),
                    [field]: coerce(
                      event.target.value,
                      fieldTypes[field],
                      model.arguments[field],
                    ),
                  }))
                }
              />
            </label>
          ))}
        </div>
      )}

      <label className="mt-3 block text-[12.5px]">
        <span className="text-muted">Comment (optional)</span>
        <Input
          className="mt-1 h-8"
          value={comment}
          maxLength={2000}
          onChange={(event) => setComment(event.target.value)}
          placeholder="Why you are approving, editing, or rejecting"
        />
      </label>

      {error && (
        <p role="alert" className="mt-2 text-[12.5px] text-danger">
          {error}
        </p>
      )}

      <div className="mt-3.5 flex flex-wrap gap-2">
        <Button size="sm" disabled={decide.isPending} onClick={() => void submit("approve")}>
          Approve
        </Button>

        {mode === "edit" ? (
          <Button
            size="sm"
            variant="secondary"
            disabled={decide.isPending}
            onClick={() => void submit("edit")}
          >
            Submit edits
          </Button>
        ) : (
          <Button
            size="sm"
            variant="secondary"
            disabled={editable.length === 0}
            onClick={() => setMode("edit")}
          >
            Edit arguments
          </Button>
        )}

        <Button
          size="sm"
          variant="ghost"
          className="text-danger"
          disabled={decide.isPending}
          onClick={() => void submit("reject")}
        >
          Reject
        </Button>
      </div>

      <p className="mt-2.5 text-[11px] leading-relaxed text-muted">
        Nothing has run yet. The server validates this decision against the live
        approval, so a stale or already-decided action is refused.
      </p>
    </section>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** Coerce text to the tool's declared type, as the schema reports it. */
export function coerce(raw: string, type: string | undefined, current: unknown): unknown {
  switch (type) {
    case "integer": {
      const parsed = Number.parseInt(raw, 10);
      return Number.isNaN(parsed) ? raw : parsed;
    }
    case "number": {
      const parsed = Number(raw);
      return Number.isNaN(parsed) ? raw : parsed;
    }
    case "boolean":
      return raw === "true" || raw === "1" || raw === "yes";
    case "array":
    case "object":
      try {
        return JSON.parse(raw);
      } catch {
        return raw;
      }
    default:
      if (typeof current === "number") {
        const parsed = Number(raw);
        return Number.isNaN(parsed) ? raw : parsed;
      }
      return raw;
  }
}
