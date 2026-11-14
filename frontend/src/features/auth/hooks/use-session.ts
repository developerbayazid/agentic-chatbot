"use client";

import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { ApiError, errorMessage } from "@/lib/api/errors";
import { setUnauthorizedHandler } from "@/lib/api/client";
import { useEffect } from "react";

export interface Session {
  authenticated: boolean;
  subject?: string;
  expiresAt?: number;
}

const SESSION_KEY = ["session"] as const;

/**
 * Session state sourced from the BFF (`/api/auth/session`), which reads the
 * HttpOnly cookie. The client never sees the token itself.
 */
export function useSession() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const query = useQuery<Session>({
    queryKey: SESSION_KEY,
    queryFn: async () => {
      const response = await fetch("/api/auth/session", {
        cache: "no-store",
      });

      if (!response.ok) {
        return { authenticated: false };
      }

      return (await response.json()) as Session;
    },
    staleTime: 30_000,
    retry: false,
  });

  const clear = useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    queryClient.clear();
    router.replace("/login");
  }, [queryClient, router]);

  // A backend 401 means the cookie is no longer accepted (expired, or the
  // signing secret changed). Drop the session instead of looping.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      queryClient.setQueryData(SESSION_KEY, { authenticated: false });
      void clear();
    });

    return () => setUnauthorizedHandler(null);
  }, [clear, queryClient]);

  const session = query.data;

  return {
    ...query,
    session,
    isAuthenticated: session?.authenticated === true,
    subject: session?.subject,
    logout: clear,
  };
}

export function sessionErrorMessage(error: unknown): string {
  if (ApiError.isApiError(error) && error.isUnauthorized) {
    return "Your session has expired. Please sign in again.";
  }

  return errorMessage(error);
}
