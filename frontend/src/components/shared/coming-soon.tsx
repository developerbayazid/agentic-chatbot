"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * Honest placeholder for a planned capability.
 *
 * It states what the feature will do and that it does not exist yet. It offers
 * no mock controls, no fake data, and no button that pretends to work — the only
 * action is returning to the chat, which does work.
 *
 * The icon is passed as a rendered node rather than a component reference: a
 * Server Component page cannot hand a function to a Client Component.
 */
export function ComingSoon({
  title,
  icon,
  summary,
  planned,
}: {
  title: string;
  icon: React.ReactNode;
  summary: string;
  planned: string[];
}) {
  return (
    <div className="mx-auto w-full max-w-2xl px-5 py-12">
      <span className="grid size-9 place-items-center rounded-lg border border-border bg-surface text-muted-strong">
        {icon}
      </span>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <h1 className="text-[19px] font-medium tracking-tight">{title}</h1>
        <span className="rounded px-1.5 py-0.5 text-[10.5px] font-medium uppercase tracking-wide text-muted ring-1 ring-inset ring-border-strong">
          Soon
        </span>
      </div>

      <p className="mt-2 max-w-xl text-[13.5px] leading-relaxed text-muted">
        {summary} This is not available yet — nothing on this page is simulated.
      </p>

      <section className="mt-6 rounded-card border border-border bg-surface p-4">
        <h2 className="text-[11px] font-medium uppercase tracking-[0.07em] text-muted">
          What it will support
        </h2>
        <ul className="mt-2.5 space-y-1.5 text-[13.5px] text-muted-strong">
          {planned.map((item) => (
            <li key={item} className="flex gap-2">
              <span aria-hidden className="text-border-strong">—</span>
              {item}
            </li>
          ))}
        </ul>
      </section>

      <Button variant="secondary" size="sm" className="mt-6" asChild>
        <Link href="/chat">
          Back to chat
          <ArrowRight />
        </Link>
      </Button>
    </div>
  );
}
