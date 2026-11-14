"use client";

import Link from "next/link";
import { AlertCircle, ShieldCheck } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/errors";
import { useApprovals } from "@/features/approvals/hooks/use-approvals";
import { ApprovalPrompt } from "@/features/approvals/components/approval-prompt";

/** Every pending human decision, across the caller's conversations. */
export default function ApprovalsPage() {
  const approvals = useApprovals();
  const pending = approvals.data ?? [];

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8">
      <header>
        <h1 className="text-[19px] font-medium tracking-tight">Approvals</h1>
        <p className="mt-1.5 max-w-xl text-[13.5px] leading-relaxed text-muted">
          Sensitive actions pause the assistant until a human decides. Nothing
          runs without a decision here.
        </p>
      </header>

      {approvals.isLoading && (
        <div className="mt-6 space-y-2">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      )}

      {approvals.isError && (
        <div className="mt-6 flex items-start gap-2 rounded-xl border border-danger/25 bg-danger-soft p-3 text-[13px]">
          <AlertCircle className="mt-0.5 size-4 text-danger" />
          <div>
            <p className="text-danger">Could not load approvals.</p>
            <p className="mt-1 text-muted">{errorMessage(approvals.error)}</p>
          </div>
        </div>
      )}

      {!approvals.isLoading && !approvals.isError && pending.length === 0 && (
        <div className="mt-6 rounded-xl border border-dashed border-border-strong px-4 py-10 text-center">
          <ShieldCheck className="mx-auto size-5 text-muted" />
          <p className="mt-2 text-[13.5px] text-muted">
            Nothing is waiting for you right now.
          </p>
        </div>
      )}

      <div className="mt-6 space-y-4">
        {pending.map((approval) => (
          <div key={approval.approval_id}>
            <ApprovalPrompt
              approval={approval}
              onDecided={() => void approvals.refetch()}
            />
            <Link
              href={`/chat/${encodeURIComponent(approval.thread_id)}`}
              className="mt-1.5 inline-block text-[12.5px] text-muted transition-colors hover:text-foreground"
            >
              Open conversation →
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
