"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { cn } from "@/lib/utils/cn";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useThreads } from "@/features/threads/hooks/use-threads";
import { ThreadRowMenu } from "@/features/threads/components/thread-actions";
import { groupThreads } from "@/features/threads/lib/group-threads";

/**
 * Recents, grouped by date the way ChatGPT does it. Compact text rows with a
 * hover-revealed context menu.
 *
 * The backend has no search endpoint, so filtering happens over the loaded list
 * (documented in API.md). While a query is active the grouping flattens — a
 * search result list gains nothing from date headers.
 */
export function ThreadList() {
  const pathname = usePathname();
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const { data: threads, isLoading, isError, refetch } = useThreads();

  const needle = query.trim().toLowerCase();

  const visible = useMemo(() => {
    if (!threads) return [];
    return needle
      ? threads.filter((thread) => thread.title.toLowerCase().includes(needle))
      : threads;
  }, [needle, threads]);

  const grouped = useMemo(
    () => (needle ? [] : groupThreads(visible)),
    [needle, visible],
  );

  const activeId = pathname.startsWith("/chat/")
    ? decodeURIComponent(pathname.slice("/chat/".length).split("/")[0] ?? "")
    : null;

  function row(threadId: string, title: string) {
    const active = threadId === activeId;

    return (
      <li key={threadId} className="group relative">
        <Link
          href={`/chat/${encodeURIComponent(threadId)}`}
          className={cn(
            "block truncate rounded-lg py-1.5 pl-2 pr-8 text-[13.5px] transition-colors",
            active
              ? "bg-surface-active text-foreground"
              : "text-muted-strong hover:bg-surface-hover hover:text-foreground",
          )}
          title={title}
        >
          {title || "New chat"}
        </Link>

        {/* Quiet at rest; appears on hover or keyboard focus. */}
        <div className="absolute inset-y-0 right-0.5 flex items-center opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
          <ThreadRowMenu threadId={threadId} title={title} />
        </div>
      </li>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-2.5 pb-1">
        <span className="text-[10.5px] font-medium uppercase tracking-[0.07em] text-muted">
          Chats
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Search chats"
          aria-expanded={searchOpen}
          onClick={() => setSearchOpen((open) => !open)}
        >
          <Search className="size-[14px]" />
        </Button>
      </div>

      {searchOpen && (
        <div className="px-2 pb-2">
          <Input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search chats"
            aria-label="Search chats"
            className="h-8 rounded-lg text-[13px]"
          />
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {isLoading && (
          <div className="space-y-1 p-1">
            <Skeleton className="h-6" />
            <Skeleton className="h-6" />
            <Skeleton className="h-6" />
          </div>
        )}

        {isError && (
          <p className="px-2 py-2 text-[12.5px] text-muted">
            Couldn&rsquo;t load chats.
            <button
              className="ml-1 text-foreground underline underline-offset-2"
              onClick={() => void refetch()}
            >
              Retry
            </button>
          </p>
        )}

        {!isLoading && !isError && visible.length === 0 && (
          <p className="px-2 py-3 text-[12.5px] leading-relaxed text-muted">
            {threads && threads.length > 0
              ? "No chat matches that search."
              : "No chats yet. Start one above."}
          </p>
        )}

        {needle && visible.length > 0 && (
          <ul className="space-y-px">{visible.map((t) => row(t.thread_id, t.title))}</ul>
        )}

        {!needle &&
          grouped.map(({ group, threads: bucket }) => (
            <section key={group} aria-label={group}>
              <h3 className="px-2 pb-1 pt-2 text-[10.5px] font-medium uppercase tracking-[0.07em] text-muted">
                {group}
              </h3>
              <ul className="space-y-px">
                {bucket.map((t) => row(t.thread_id, t.title))}
              </ul>
            </section>
          ))}
      </div>
    </div>
  );
}
