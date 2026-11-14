"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, SquarePen } from "lucide-react";
import { useMemo, useState } from "react";

import { cn } from "@/lib/utils/cn";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useThreads } from "@/features/threads/hooks/use-threads";
import { ThreadRowMenu } from "@/features/threads/components/thread-actions";

/**
 * Recent conversations. Compact text rows with a quiet context menu.
 * The backend has no search endpoint, so filtering is over the loaded list.
 */
export function ThreadList() {
  const pathname = usePathname();
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const { data: threads, isLoading, isError, refetch } = useThreads();

  const visible = useMemo(() => {
    if (!threads) return [];

    const needle = query.trim().toLowerCase();
    return needle
      ? threads.filter((t) => t.title.toLowerCase().includes(needle))
      : threads;
  }, [query, threads]);

  const activeId = pathname.startsWith("/chat/")
    ? decodeURIComponent(pathname.slice("/chat/".length).split("/")[0] ?? "")
    : null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-2.5 pb-1 pt-1">
        <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-muted">
          Recents
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Search conversations"
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
            aria-label="Search conversations"
            className="h-8 text-[13px]"
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
              className="ml-1 text-accent underline-offset-2 hover:underline"
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
              : "No chats yet. Start one below."}
          </p>
        )}

        <ul className="space-y-px">
          {visible.map((thread) => {
            const active = thread.thread_id === activeId;

            return (
              <li key={thread.thread_id} className="group relative">
                <Link
                  href={`/chat/${encodeURIComponent(thread.thread_id)}`}
                  className={cn(
                    "block truncate rounded-md py-1.5 pl-2 pr-8 text-[13.5px] transition-colors",
                    active
                      ? "bg-surface-hover text-foreground"
                      : "text-muted-strong hover:bg-surface-hover hover:text-foreground",
                  )}
                  title={thread.title}
                >
                  {thread.title || "New chat"}
                </Link>

                {/* Appears on hover/focus so the row stays quiet at rest. */}
                <div className="absolute inset-y-0 right-0.5 flex items-center opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                  <ThreadRowMenu threadId={thread.thread_id} title={thread.title} />
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="px-2 pb-1">
        <Link
          href="/chat"
          className="flex items-center gap-1.5 rounded-md px-1 py-1 text-[12.5px] text-muted transition-colors hover:text-foreground"
        >
          <SquarePen className="size-3.5" />
          New chat
        </Link>
      </div>
    </div>
  );
}
