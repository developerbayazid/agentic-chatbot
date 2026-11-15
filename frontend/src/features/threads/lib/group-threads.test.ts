import { describe, expect, it } from "vitest";

import {
  groupFor,
  groupThreads,
  parseTimestamp,
} from "@/features/threads/lib/group-threads";
import type { Thread } from "@/types/api";

const NOW = new Date("2026-11-15T12:00:00Z");

function thread(id: string, updated: string | null): Thread {
  return {
    thread_id: id,
    title: id,
    created_at: updated,
    updated_at: updated,
  };
}

describe("parseTimestamp", () => {
  it("treats a bare SQLite timestamp as UTC", () => {
    const parsed = parseTimestamp("2026-11-15 09:00:00");

    expect(parsed?.toISOString()).toBe("2026-11-15T09:00:00.000Z");
  });

  it("respects an explicit offset", () => {
    const parsed = parseTimestamp("2026-11-15T09:00:00+06:00");

    expect(parsed?.toISOString()).toBe("2026-11-15T03:00:00.000Z");
  });

  it("returns null for null, empty, or garbage", () => {
    expect(parseTimestamp(null)).toBeNull();
    expect(parseTimestamp("")).toBeNull();
    expect(parseTimestamp("not a date")).toBeNull();
  });
});

describe("groupFor", () => {
  it("buckets by recency", () => {
    expect(groupFor("2026-11-15 10:00:00", NOW)).toBe("Today");
    expect(groupFor("2026-11-14 10:00:00", NOW)).toBe("Yesterday");
    expect(groupFor("2026-11-11 10:00:00", NOW)).toBe("Previous 7 days");
    expect(groupFor("2026-10-25 10:00:00", NOW)).toBe("Previous 30 days");
    expect(groupFor("2026-01-01 10:00:00", NOW)).toBe("Older");
  });

  it("treats a future or unknown timestamp sensibly", () => {
    expect(groupFor("2026-11-16 10:00:00", NOW)).toBe("Today");
    expect(groupFor(null, NOW)).toBe("Older");
  });
});

describe("groupThreads", () => {
  it("groups in order and omits empty buckets", () => {
    const grouped = groupThreads(
      [
        thread("today-1", "2026-11-15 11:00:00"),
        thread("today-2", "2026-11-15 09:00:00"),
        thread("yesterday", "2026-11-14 10:00:00"),
        thread("old", "2026-01-01 10:00:00"),
      ],
      NOW,
    );

    expect(grouped.map((bucket) => bucket.group)).toEqual([
      "Today",
      "Yesterday",
      "Older",
    ]);
    // Newest-first order inside a bucket is preserved.
    expect(grouped[0].threads.map((item) => item.thread_id)).toEqual([
      "today-1",
      "today-2",
    ]);
  });

  it("handles an empty list", () => {
    expect(groupThreads([], NOW)).toEqual([]);
  });
});
