"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { request } from "@/lib/api/client";
import type { DocumentListResponse, IngestResponse } from "@/types/api";

export const documentKeys = { list: ["documents"] as const };

/** `GET /api/v1/documents` — the caller's documents only. */
export function useDocuments() {
  return useQuery({
    queryKey: documentKeys.list,
    queryFn: () => request<DocumentListResponse>("/api/v1/documents"),
  });
}

/**
 * `POST /api/v1/documents` (multipart).
 *
 * Uploading and indexing are the same request: `chunks_created` / `skipped`
 * in the response describe what the backend actually did.
 */
export function useUploadDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);

      return request<IngestResponse>("/api/v1/documents", {
        method: "POST",
        form,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: documentKeys.list });
    },
  });
}

/** `DELETE /api/v1/documents/{doc_id}` — also prunes its vectors. */
export function useDeleteDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (docId: string) =>
      request<void>(`/api/v1/documents/${encodeURIComponent(docId)}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: documentKeys.list });
    },
  });
}
