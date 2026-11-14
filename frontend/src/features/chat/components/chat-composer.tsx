"use client";

import { useCallback, useEffect, useRef } from "react";
import { ArrowUp, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils/cn";

/**
 * Claude-style composer: a large white surface with a thin border, rounded
 * corners, a subtle focus state, and the controls inside the field.
 *
 * Fully controlled: the parent owns the draft, so the welcome screen can seed an
 * example prompt and sending can clear it without mirroring the text twice.
 *
 * Enter sends, Shift+Enter inserts a newline, and the field grows with its
 * content up to a cap.
 */
export function ChatComposer({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
  disabled,
  placeholder = "How can I help you today?",
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: (message: string) => void;
  onStop: () => void;
  streaming: boolean;
  disabled?: boolean;
  placeholder?: string;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const element = textareaRef.current;

    if (!element) return;

    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 240)}px`;
  }, []);

  useEffect(resize, [resize, value]);

  function submit() {
    const message = value.trim();

    if (!message || streaming || disabled) return;

    onSend(message);
    onChange("");
  }

  return (
    <div className="bg-background px-4 pb-4 pt-2">
      <div className="mx-auto w-full max-w-3xl">
        <div
          className={cn(
            "flex items-end gap-1.5 rounded-composer border border-border bg-surface-raised",
            "px-3 py-2.5 transition-colors focus-within:border-border-strong",
            disabled && "opacity-70",
          )}
        >
          <textarea
            ref={textareaRef}
            value={value}
            rows={1}
            placeholder={placeholder}
            aria-label="Message"
            disabled={disabled}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            className={cn(
              "min-h-7 flex-1 resize-none bg-transparent px-0.5 py-1 text-[15px] leading-relaxed",
              "text-foreground outline-none placeholder:text-muted/80 disabled:opacity-60",
            )}
          />

          {streaming ? (
            <Button
              variant="secondary"
              size="icon"
              className="size-8 rounded-lg"
              aria-label="Stop generating"
              title="Stop generating"
              onClick={onStop}
            >
              <Square className="size-3.5" />
            </Button>
          ) : (
            <Button
              size="icon"
              className="size-8 rounded-lg"
              aria-label="Send message"
              title="Send message"
              disabled={!value.trim() || disabled}
              onClick={submit}
            >
              <ArrowUp className="size-4" />
            </Button>
          )}
        </div>

        <p className="mt-2 text-center text-[11.5px] text-muted/80">
          BAYAZID AI can make mistakes. Sensitive actions require your approval.
        </p>
      </div>
    </div>
  );
}
