import type { Thread } from "@/types/api";

/** Buckets a conversation list the way ChatGPT groups recents. */
export const DATE_GROUPS = [
  "Today",
  "Yesterday",
  "Previous 7 days",
  "Previous 30 days",
  "Older",
] as const;

export type DateGroup = (typeof DATE_GROUPS)[number];

export interface GroupedThreads {
  group: DateGroup;
  threads: Thread[];
}

/**
 * Parse a backend timestamp.
 *
 * SQLite `CURRENT_TIMESTAMP` yields `"YYYY-MM-DD HH:MM:SS"` (UTC, no zone). A
 * bare `new Date(str)` treats that as local time on some engines and invalid on
 * others, so the space is normalised to `T` and `Z` appended when no offset is
 * present.
 */
export function parseTimestamp(value: string | null): Date | null {
  if (!value) return null;

  const normalised = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value)
    ? value.replace(" ", "T")
    : `${value.replace(" ", "T")}Z`;

  const date = new Date(normalised);

  return Number.isNaN(date.getTime()) ? null : date;
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** Which bucket a timestamp falls into, relative to `now`. */
export function groupFor(value: string | null, now = new Date()): DateGroup {
  const date = parseTimestamp(value);

  if (!date) return "Older";

  const days = Math.floor((startOfDay(now) - startOfDay(date)) / 86_400_000);

  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days <= 7) return "Previous 7 days";
  if (days <= 30) return "Previous 30 days";

  return "Older";
}

/**
 * Group conversations by recency, preserving the backend's newest-first order
 * inside each bucket and omitting empty buckets entirely.
 */
export function groupThreads(threads: Thread[], now = new Date()): GroupedThreads[] {
  const buckets = new Map<DateGroup, Thread[]>();

  for (const thread of threads) {
    const group = groupFor(thread.updated_at ?? thread.created_at, now);
    const existing = buckets.get(group);

    if (existing) {
      existing.push(thread);
    } else {
      buckets.set(group, [thread]);
    }
  }

  return DATE_GROUPS.filter((group) => buckets.has(group)).map((group) => ({
    group,
    threads: buckets.get(group) as Thread[],
  }));
}
