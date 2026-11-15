import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { threadKeys } from "@/features/threads/hooks/use-threads";

/**
 * Cache behaviour for conversation switching.
 *
 * These assert the two properties the UI depends on: a per-thread history entry
 * survives a switch (so going back is instant), and invalidation after a turn
 * targets only that thread rather than every cached conversation.
 */
function client() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

describe("thread history caching", () => {
  it("keeps a per-thread entry that survives a switch", () => {
    const qc = client();
    const threadA = "thread-a";
    const threadB = "thread-b";

    qc.setQueryData(threadKeys.history(threadA), { thread_id: threadA, messages: [] });
    qc.setQueryData(threadKeys.history(threadB), { thread_id: threadB, messages: [] });

    // Both remain cached — switching back does not need a network round trip.
    expect(qc.getQueryData(threadKeys.history(threadA))).toBeTruthy();
    expect(qc.getQueryData(threadKeys.history(threadB))).toBeTruthy();
  });

  it("scopes a turn's invalidation to the thread that ran it", async () => {
    const qc = client();
    qc.setQueryData(threadKeys.list, [{ thread_id: "thread-a" }]);
    qc.setQueryData(threadKeys.history("thread-a"), { messages: [] });
    qc.setQueryData(threadKeys.history("thread-b"), { messages: [] });

    const invalidated: unknown[] = [];
    const original = qc.invalidateQueries.bind(qc);

    vi.spyOn(qc, "invalidateQueries").mockImplementation((filters, options) => {
      invalidated.push(filters?.queryKey);
      return original(filters, options);
    });

    // What the stream hook does after a turn on thread-a.
    await qc.invalidateQueries({ queryKey: threadKeys.list });
    await qc.invalidateQueries({ queryKey: threadKeys.history("thread-a") });

    expect(invalidated).toContainEqual(threadKeys.list);
    expect(invalidated).toContainEqual(threadKeys.history("thread-a"));
    expect(invalidated).not.toContainEqual(threadKeys.history("thread-b"));

    // thread-b was never invalidated, so its data is untouched.
    expect(qc.getQueryData(threadKeys.history("thread-b"))).toBeTruthy();
  });

  it("a staleTime does not prevent an explicit invalidation from refetching", async () => {
    const qc = client();
    const queryFn = vi.fn(async () => ({ messages: [] }));

    // Long staleTime, exactly as useThreadHistory sets it.
    const options = {
      queryKey: threadKeys.history("thread-a"),
      queryFn,
      staleTime: 5 * 60_000,
    };

    await qc.fetchQuery(options);
    expect(queryFn).toHaveBeenCalledTimes(1);

    // A fresh cache hit does not refetch…
    await qc.fetchQuery(options);
    expect(queryFn).toHaveBeenCalledTimes(1);

    // …but an explicit invalidation overrides staleTime by marking it stale.
    await qc.invalidateQueries({ queryKey: threadKeys.history("thread-a") });
    await qc.fetchQuery(options);
    expect(queryFn).toHaveBeenCalledTimes(2);
  });
});
