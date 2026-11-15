"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { request } from "@/lib/api/client";
import type {
  Thread,
  ThreadHistoryResponse,
  ThreadListResponse,
} from "@/types/api";

export const threadKeys = {
  list: ["threads"] as const,
  detail: (threadId: string) => ["threads", threadId] as const,
  history: (threadId: string) => ["threads", threadId, "history"] as const,
};

/** `GET /api/v1/threads` — already scoped to the caller by the backend. */
export function useThreads() {
  return useQuery({
    queryKey: threadKeys.list,
    queryFn: async () => {
      const data = await request<ThreadListResponse>("/api/v1/threads");
      return data.threads;
    },
  });
}

/** `GET /api/v1/threads/{id}/history` — restored conversation turns. */
export function useThreadHistory(threadId: string | null) {
  return useQuery({
    queryKey: threadId ? threadKeys.history(threadId) : ["threads", "none"],
    enabled: Boolean(threadId),
    queryFn: () =>
      request<ThreadHistoryResponse>(
        `/api/v1/threads/${encodeURIComponent(threadId as string)}/history`,
      ),
    // A conversation's stored history does not change unless this client sends a
    // turn, so it stays fresh long enough to make switching back instant.
    staleTime: 5 * 60_000,
    // Keep visited conversations cached for the session; evicting them would
    // make switching back a full re-fetch.
    gcTime: 30 * 60_000,
  });
}

/** `PATCH /api/v1/threads/{id}` — rename. */
export function useRenameThread() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ threadId, title }: { threadId: string; title: string }) =>
      request<Thread>(`/api/v1/threads/${encodeURIComponent(threadId)}`, {
        method: "PATCH",
        json: { title },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: threadKeys.list });
    },
  });
}

/** `DELETE /api/v1/threads/{id}` — removes checkpoints and metadata. */
export function useDeleteThread() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (threadId: string) =>
      request<void>(`/api/v1/threads/${encodeURIComponent(threadId)}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: threadKeys.list });
    },
  });
}
