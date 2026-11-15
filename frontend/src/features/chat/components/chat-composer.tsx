"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils/cn";
import { CommandMenu } from "@/features/commands/components/command-menu";
import type { CommandDefinition } from "@/features/commands/registry";

/**
 * Composer with a `/` command menu.
 *
 * The menu opens only while the draft is a single line beginning with `/`, so
 * ordinary prose that happens to contain a slash never triggers it. While open,
 * Up/Down/Enter/Escape belong to the menu, not the textarea.
 */
export function ChatComposer({
  value,
  onChange,
  onSend,
  onStop,
  onCommand,
  filterCommands,
  streaming,
  disabled,
  placeholder = "How can I help you today?",
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: (message: string) => void;
  onStop: () => void;
  onCommand: (command: CommandDefinition) => void;
  filterCommands: (query: string) => CommandDefinition[];
  streaming: boolean;
  disabled?: boolean;
  placeholder?: string;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  const isCommandDraft = /^\/\S*$/.test(value.trim()) || value.trim() === "/";
  const matches = menuOpen && isCommandDraft ? filterCommands(value) : [];

  const resize = useCallback(() => {
    const element = textareaRef.current;
    if (!element) return;

    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 240)}px`;
  }, []);

  useEffect(resize, [resize, value]);

  function choose(command: CommandDefinition) {
    setMenuOpen(false);
    setActiveIndex(0);
    onCommand(command);
    onChange("");
  }

  function submit() {
    const message = value.trim();
    if (!message || streaming || disabled) return;

    onSend(message);
    onChange("");
    setMenuOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (menuOpen && matches.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((index) => (index + 1) % matches.length);
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((index) => (index - 1 + matches.length) % matches.length);
        return;
      }

      if (event.key === "Enter") {
        event.preventDefault();
        choose(matches[Math.min(activeIndex, matches.length - 1)]);
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
        return;
      }
    }

    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="bg-background px-4 pb-4 pt-2">
      <div className="mx-auto w-full max-w-3xl">
        {menuOpen && isCommandDraft && (
          <CommandMenu
            commands={matches}
            activeIndex={activeIndex}
            onSelect={choose}
            onHover={setActiveIndex}
            onClose={() => setMenuOpen(false)}
          />
        )}

        <div
          className={cn(
            // Fully rounded, like ChatGPT's composer. `rounded-full` with the
            // generous horizontal padding keeps the pill shape even as the text
            // grows; the textarea's own max-height caps how tall it gets.
            "flex items-end gap-2 rounded-[1.75rem] border border-border-strong",
            "bg-background py-2 pl-5 pr-2",
            "transition-colors focus-within:border-foreground/40",
            disabled && "opacity-70",
          )}
        >
          <textarea
            ref={textareaRef}
            value={value}
            rows={1}
            placeholder={placeholder}
            aria-label="Message"
            aria-autocomplete="list"
            aria-controls="slash-command-menu"
            disabled={disabled}
            onChange={(event) => {
              const next = event.target.value;
              onChange(next);
              // Open on a leading slash, close once it stops looking like one.
              // The highlight resets here rather than in an effect, so typing
              // never triggers a cascading render.
              setMenuOpen(/^\/\S*$/.test(next.trim()) || next === "/");
              setActiveIndex(0);
            }}
            onKeyDown={onKeyDown}
            className={cn(
              "min-h-7 flex-1 resize-none bg-transparent px-0.5 py-1 text-[15px] leading-relaxed",
              "text-foreground outline-none placeholder:text-muted/80 disabled:opacity-60",
            )}
          />

          {streaming ? (
            <Button
              variant="secondary"
              size="icon"
              className="size-9 shrink-0 rounded-full"
              aria-label="Stop generating"
              title="Stop generating"
              onClick={onStop}
            >
              <Square className="size-3.5" />
            </Button>
          ) : (
            <Button
              size="icon"
              className="size-9 shrink-0 rounded-full"
              aria-label="Send message"
              title="Send message"
              disabled={!value.trim() || disabled}
              onClick={submit}
            >
              <ArrowUp className="size-4" />
            </Button>
          )}
        </div>

        <p className="mt-2 text-center text-[11px] text-muted">
          Type <span className="font-mono">/</span> for commands · Enter to send ·
          Shift+Enter for a new line
        </p>
      </div>
    </div>
  );
}
