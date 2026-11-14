import * as React from "react";

import { cn } from "@/lib/utils/cn";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

/** Thin neutral border; the accent appears only on focus. */
export function Input({ className, type = "text", ...props }: InputProps) {
  return (
    <input
      type={type}
      className={cn(
        "flex h-9 w-full rounded-lg border border-border bg-background px-3 py-1 text-sm text-foreground",
        "placeholder:text-muted/70 transition-colors",
        "hover:border-border-strong focus-visible:border-accent",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
