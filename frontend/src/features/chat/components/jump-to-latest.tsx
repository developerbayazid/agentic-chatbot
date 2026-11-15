"use client";

import { ArrowDown } from "lucide-react";

import { cn } from "@/lib/utils/cn";

/**
 * Appears only when the reader has scrolled away from the newest message, so
 * following the conversation never requires chasing the viewport.
 */
export function JumpToLatest({
  visible,
  unseen,
  onClick,
}: {
  visible: boolean;
  unseen: number;
  onClick: () => void;
}) {
  return (
    <div
      className={cn(
        "pointer-events-none sticky bottom-3 z-10 flex justify-center",
        "transition-opacity duration-150",
        visible ? "opacity-100" : "opacity-0",
      )}
      aria-hidden={!visible}
    >
      <button
        type="button"
        onClick={onClick}
        tabIndex={visible ? 0 : -1}
        className={cn(
          "pointer-events-auto flex items-center gap-1.5 rounded-full border border-border-strong",
          "bg-background px-3 py-1.5 text-[12px] font-medium text-foreground shadow-sm",
          "transition-colors hover:bg-surface-hover",
        )}
      >
        <ArrowDown className="size-3.5" />
        {unseen > 0 ? `${unseen} new message${unseen === 1 ? "" : "s"}` : "Jump to latest"}
      </button>
    </div>
  );
}
