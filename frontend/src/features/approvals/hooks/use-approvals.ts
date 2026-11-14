"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { request } from "@/lib/api/client";
import { threadKeys } from "@/features/threads/hooks/use-threads";
import type {
  ApprovalDetail,
  ApprovalSummary,
  DecisionRequest,
  DecisionResponse,
} from "@/types/api";

export const approvalKeys = {
  list: ["approvals"] as const,
  detail: (approvalId: string) => ["approvals", approvalId] as const,
};

/** `GET /api/v1/approvals` — the caller's pending approvals. */
export function useApprovals() {
  return useQuery({
    queryKey: approvalKeys.list,
    queryFn: () => request<ApprovalSummary[]>("/api/v1/approvals"),
  });
}

/**
 * The pending approval for one conversation, resolved from the approvals list.
 * This is how an interruption that happened in an earlier turn (or another
 * client) is surfaced, rather than inferring it from a stream we never saw.
 */
export function useApproval(threadId: string | null) {
  const query = useApprovals();
  const pending =
    query.data?.find((approval) => approval.thread_id === threadId) ?? null;

  return { ...query, data: pending };
}

/** `GET /api/v1/approvals/{id}` — adds editable fields and details. */
export function useApprovalDetail(approvalId: string | null) {
  return useQuery({
    queryKey: approvalId
      ? approvalKeys.detail(approvalId)
      : ["approvals", "none"],
    enabled: Boolean(approvalId),
    queryFn: () =>
      request<ApprovalDetail>(
        `/api/v1/approvals/${encodeURIComponent(approvalId as string)}`,
      ),
  });
}

/** `POST /api/v1/approvals/{id}/decision` — the only way an action executes. */
export function useDecideApproval() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      approvalId,
      decision,
    }: { approvalId: string; decision: DecisionRequest }) =>
      request<DecisionResponse>(
        `/api/v1/approvals/${encodeURIComponent(approvalId)}/decision`,
        { method: "POST", json: decision },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: approvalKeys.list });
      void queryClient.invalidateQueries({ queryKey: threadKeys.list });
    },
  });
}
