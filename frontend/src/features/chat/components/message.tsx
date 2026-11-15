"use client";

import { memo, useState } from "react";
import { Check, Copy } from "lucide-react";

import { cn } from "@/lib/utils/cn";
import { MarkdownMessage } from "@/components/shared/markdown-message";

/**
 * Message rows are memoised.
 *
 * A streaming turn re-renders its parent on every token; without `memo`, every
 * restored message in a long conversation would be reconciled each time. The
 * props are primitives, so the default shallow comparison is sufficient.
 */

/** User turns: plain text, right-aligned in a very light block. */
export const UserMessage = memo(function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap break-words rounded-2xl bg-user-bubble",
          "px-4 py-2.5 text-[15px] leading-relaxed text-foreground",
        )}
      >
        {content}
      </div>
    </div>
  );
});

/**
 * Assistant turns: no card. Typography and spacing carry the hierarchy, exactly
 * because the response is the main content of the page.
 */
export const AssistantMessage = memo(function AssistantMessage({
  content,
  streaming = false,
}: {
  content: string;
  streaming?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard may be unavailable; the text stays selectable.
    }
  }

  return (
    <div className="group relative">
      <MarkdownMessage content={content} />

      {streaming && (
        <span
          aria-hidden
          className="ml-0.5 inline-block h-[1.05em] w-[2px] animate-pulse rounded-full bg-foreground/60 align-baseline"
        />
      )}

      {!streaming && content && (
        <div className="mt-1.5 flex gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
          <button
            type="button"
            onClick={() => void copy()}
            className="flex items-center gap-1 rounded px-1 py-0.5 text-[11.5px] text-muted hover:bg-surface-hover hover:text-foreground"
            aria-label={copied ? "Copied" : "Copy response"}
          >
            {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      )}
    </div>
  );
});

/** Historical tool output, shown as a quiet monospace line. */
export const ToolLine = memo(function ToolLine({ content }: { content: string }) {
  return <p className="font-mono text-[11.5px] text-muted">{content}</p>;
});
