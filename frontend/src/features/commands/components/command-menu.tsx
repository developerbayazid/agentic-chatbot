"use client";

import { useEffect, useRef } from "react";
import { CornerDownLeft } from "lucide-react";

import { cn } from "@/lib/utils/cn";
import {
  CATEGORY_LABELS,
  type CommandDefinition,
} from "@/features/commands/registry";

/**
 * The `/` menu.
 *
 * Keyboard-first: arrows move, Enter selects, Escape closes. Mouse selection is
 * supported for discoverability. Planned commands are listed but visually
 * marked, so the menu doubles as an accurate statement of what exists today.
 */
export function CommandMenu({
  commands,
  activeIndex,
  onSelect,
  onHover,
  onClose,
}: {
  commands: CommandDefinition[];
  activeIndex: number;
  onSelect: (command: CommandDefinition) => void;
  onHover: (index: number) => void;
  onClose: () => void;
}) {
  const listRef = useRef<HTMLUListElement>(null);

  // Keep the highlighted row visible without moving the page. Guarded because
  // `scrollIntoView` is absent in some environments (jsdom among them), and
  // losing the highlight-scroll is far better than throwing during a keystroke.
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;

    const active = list.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`);
    active?.scrollIntoView?.({ block: "nearest" });
  }, [activeIndex]);

  if (commands.length === 0) {
    return (
      <div className="mb-2 rounded-card border border-border bg-background px-3 py-2.5 text-[12.5px] text-muted">
        No command matches that.
        <button
          type="button"
          className="ml-1 text-foreground underline underline-offset-2"
          onClick={onClose}
        >
          Dismiss
        </button>
      </div>
    );
  }

  // Where each category first appears, computed without mutating anything that
  // outlives the render.
  const headerAt = commands.map(
    (command, index) =>
      index === 0 || commands[index - 1].category !== command.category,
  );

  return (
    <div
      id="slash-command-menu"
      role="listbox"
      aria-label="Slash commands"
      className="mb-2 overflow-hidden rounded-card border border-border bg-background shadow-sm"
    >
      <ul ref={listRef} className="scroll-area max-h-72 overflow-y-auto py-1">
        {commands.map((command, index) => {
          const active = index === activeIndex;
          const planned = command.availability === "planned";

          return (
            <li key={command.name}>
              {headerAt[index] && (
                <p className="px-3 pb-0.5 pt-2 text-[10px] font-medium uppercase tracking-[0.07em] text-muted">
                  {CATEGORY_LABELS[command.category]}
                </p>
              )}

              <button
                type="button"
                data-index={index}
                role="option"
                aria-selected={active}
                onMouseEnter={() => onHover(index)}
                // `onMouseDown` prevents the textarea from losing focus first.
                onMouseDown={(event) => {
                  event.preventDefault();
                  onSelect(command);
                }}
                className={cn(
                  "flex w-full items-center gap-3 px-3 py-1.5 text-left transition-colors",
                  active ? "bg-surface-active" : "hover:bg-surface-hover",
                )}
              >
                <span
                  className={cn(
                    "w-[7.5rem] shrink-0 font-mono text-[12.5px]",
                    planned ? "text-muted" : "text-foreground",
                  )}
                >
                  {command.name}
                </span>

                <span className="min-w-0 flex-1 truncate text-[12.5px] text-muted">
                  {command.description}
                </span>

                {planned ? (
                  <span className="shrink-0 rounded px-1 py-px text-[10px] font-medium uppercase tracking-wide text-muted ring-1 ring-inset ring-border-strong">
                    Soon
                  </span>
                ) : (
                  active && (
                    <CornerDownLeft className="size-3 shrink-0 text-muted" aria-hidden />
                  )
                )}
              </button>
            </li>
          );
        })}
      </ul>

      <p className="border-t border-border px-3 py-1.5 text-[10.5px] text-muted">
        ↑↓ to navigate · Enter to select · Esc to close
      </p>
    </div>
  );
}
