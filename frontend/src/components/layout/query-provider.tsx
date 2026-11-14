"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";

/**
 * Server state lives here rather than in Zustand: TanStack Query owns caching,
 * retries, and refetching of backend data.
 */
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            refetchOnWindowFocus: false,
            // A 401 is a session problem, not a transient failure.
            retry: (failureCount, error) =>
              !(ApiError.isApiError(error) && error.status === 401) &&
              failureCount < 2,
          },
          mutations: { retry: false },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
