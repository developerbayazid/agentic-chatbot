"use client";

import * as React from "react";
import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";

import { cn } from "@/lib/utils/cn";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const AlertDialog = AlertDialogPrimitive.Root;
export const AlertDialogTrigger = AlertDialogPrimitive.Trigger;

interface DialogInput {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  maxLength?: number;
}

function Shell({
  title,
  description,
  confirmLabel,
  destructive,
  onConfirm,
  input,
}: {
  title: string;
  description: string;
  confirmLabel: string;
  destructive: boolean;
  onConfirm: () => void;
  input?: DialogInput;
}) {
  return (
    <AlertDialogPrimitive.Portal>
      <AlertDialogPrimitive.Overlay className="fixed inset-0 z-50 bg-foreground/25" />
      <AlertDialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[min(92vw,26rem)] -translate-x-1/2 -translate-y-1/2",
          "rounded-card border border-border bg-surface-raised p-5 shadow-lg",
        )}
      >
        <AlertDialogPrimitive.Title className="text-[15px] font-medium text-foreground">
          {title}
        </AlertDialogPrimitive.Title>
        <AlertDialogPrimitive.Description className="mt-1.5 text-[13px] leading-relaxed text-muted">
          {description}
        </AlertDialogPrimitive.Description>

        {input && (
          <Input
            autoFocus
            className="mt-3"
            value={input.value}
            maxLength={input.maxLength}
            placeholder={input.placeholder}
            onChange={(event) => input.onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") onConfirm();
            }}
          />
        )}

        <div className="mt-5 flex justify-end gap-2">
          <AlertDialogPrimitive.Cancel asChild>
            <Button variant="ghost" size="sm">
              Cancel
            </Button>
          </AlertDialogPrimitive.Cancel>
          <AlertDialogPrimitive.Action asChild>
            <Button
              size="sm"
              variant={destructive ? "danger" : "default"}
              onClick={onConfirm}
            >
              {confirmLabel}
            </Button>
          </AlertDialogPrimitive.Action>
        </div>
      </AlertDialogPrimitive.Content>
    </AlertDialogPrimitive.Portal>
  );
}

export function ConfirmDialog({
  trigger,
  title,
  description,
  confirmLabel = "Confirm",
  destructive = false,
  onConfirm,
}: {
  trigger: React.ReactNode;
  title: string;
  description: string;
  confirmLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
}) {
  return (
    <AlertDialogPrimitive.Root>
      <AlertDialogPrimitive.Trigger asChild>{trigger}</AlertDialogPrimitive.Trigger>
      <Shell
        title={title}
        description={description}
        confirmLabel={confirmLabel}
        destructive={destructive}
        onConfirm={onConfirm}
      />
    </AlertDialogPrimitive.Root>
  );
}

/**
 * The same dialog driven by state rather than a trigger element, for menus whose
 * items close themselves before a confirmation can be shown. Optionally renders
 * a single text field, which is how an inline rename is collected.
 */
export function ControlledConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  destructive = false,
  onConfirm,
  input,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  input?: DialogInput;
}) {
  return (
    <AlertDialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <Shell
        title={title}
        description={description}
        confirmLabel={confirmLabel}
        destructive={destructive}
        onConfirm={onConfirm}
        input={input}
      />
    </AlertDialogPrimitive.Root>
  );
}
