"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ShieldCheck, Wrench } from "lucide-react";

import { request } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { ToolListResponse } from "@/types/tools";

/**
 * The tools the assistant can actually call, read from the backend catalog.
 *
 * This is a reference view, not a control surface: tools run inside a graph
 * turn, and the ones marked with a shield still require human approval.
 */
export default function ToolsPage() {
  const [query, setQuery] = useState("");

  const catalog = useQuery({
    queryKey: ["tools"],
    queryFn: () => request<ToolListResponse>("/api/v1/tools"),
  });

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const tools = (catalog.data?.tools ?? []).filter(
      (tool) =>
        !needle ||
        tool.name.toLowerCase().includes(needle) ||
        tool.description.toLowerCase().includes(needle) ||
        tool.category.toLowerCase().includes(needle),
    );

    const buckets = new Map<string, typeof tools>();

    for (const tool of tools) {
      const existing = buckets.get(tool.category);
      if (existing) existing.push(tool);
      else buckets.set(tool.category, [tool]);
    }

    return [...buckets.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [catalog.data, query]);

  const total = catalog.data?.count ?? 0;
  const gated = catalog.data?.tools.filter((tool) => tool.requires_approval).length ?? 0;

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8">
      <header>
        <h1 className="text-[19px] font-medium tracking-tight">Tools</h1>
        <p className="mt-1.5 max-w-xl text-[13.5px] leading-relaxed text-muted">
          What the assistant can call while answering. Tools marked with a shield
          pause for your approval before they run.
        </p>
        {total > 0 && (
          <p className="mt-2 text-[12.5px] text-muted">
            {total} tools · {gated} require approval
          </p>
        )}
      </header>

      <div className="mt-5">
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter tools"
          aria-label="Filter tools"
          className="h-9 max-w-sm"
        />
      </div>

      {catalog.isLoading && (
        <div className="mt-5 space-y-1.5">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      )}

      {catalog.isError && (
        <div className="mt-5 flex items-start gap-2 rounded-card border border-danger/25 bg-danger-soft p-3 text-[13px]">
          <AlertCircle className="mt-0.5 size-4 text-danger" />
          <div>
            <p className="text-danger">Could not load the tool catalog.</p>
            <p className="mt-1 text-muted">{errorMessage(catalog.error)}</p>
          </div>
        </div>
      )}

      {!catalog.isLoading && !catalog.isError && groups.length === 0 && (
        <p className="mt-6 text-[13.5px] text-muted">No tool matches that filter.</p>
      )}

      <div className="mt-6 space-y-6">
        {groups.map(([category, tools]) => (
          <section key={category} aria-label={category}>
            <h2 className="mb-1.5 text-[10.5px] font-medium uppercase tracking-[0.07em] text-muted">
              {category} · {tools.length}
            </h2>

            <ul className="divide-y divide-border">
              {tools.map((tool) => (
                <li key={tool.name} className="flex items-start gap-3 py-2.5">
                  <Wrench className="mt-0.5 size-3.5 shrink-0 text-muted" />

                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 font-mono text-[12.5px] text-foreground">
                      {tool.name}
                      {tool.requires_approval && (
                        <span
                          className="inline-flex items-center gap-0.5 rounded px-1 py-px text-[10px] font-medium uppercase tracking-wide text-warning ring-1 ring-inset ring-warning/40"
                          title="Pauses for human approval before it runs"
                        >
                          <ShieldCheck className="size-2.5" />
                          Approval
                        </span>
                      )}
                    </p>
                    {tool.description && (
                      <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted">
                        {tool.description}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
