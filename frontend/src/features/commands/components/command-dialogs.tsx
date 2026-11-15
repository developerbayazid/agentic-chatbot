"use client";

import { useState } from "react";

import { ControlledConfirmDialog } from "@/components/ui/confirm-dialog";
import type { CommandDialogState } from "@/features/commands/hooks/use-commands";

/**
 * Rename field, remounted via `key` whenever the target conversation changes.
 *
 * Initialising the draft from a prop here (rather than syncing it in an effect)
 * keeps the state derived from the dialog that opened it, with no cascading
 * render and no chance of showing a previous conversation's title.
 */
function RenameDialog({
  open,
  initialTitle,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  initialTitle: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: (title: string) => void;
}) {
  const [title, setTitle] = useState(initialTitle);

  return (
    <ControlledConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Rename conversation"
      description="A short title, 1–100 characters."
      confirmLabel="Save"
      input={{
        value: title,
        onChange: setTitle,
        maxLength: 100,
        placeholder: "Conversation title",
      }}
      onConfirm={() => {
        const next = title.trim();
        if (next) onConfirm(next);
      }}
    />
  );
}

/**
 * The rename and delete confirmations reached from `/rename` and `/delete`.
 *
 * Both actions go through the existing thread endpoints; deleting is destructive,
 * so it is always confirmed and never inferred from a bare command.
 */
export function CommandDialogs({
  dialog,
  onClose,
  onRename,
  onDelete,
}: {
  dialog: CommandDialogState | null;
  onClose: () => void;
  onRename: (title: string) => void;
  onDelete: () => void;
}) {
  return (
    <>
      <RenameDialog
        key={dialog?.kind === "rename" ? dialog.threadId : "no-rename"}
        open={dialog?.kind === "rename"}
        initialTitle={dialog?.kind === "rename" ? dialog.title : ""}
        onOpenChange={(open) => {
          if (!open) onClose();
        }}
        onConfirm={onRename}
      />

      <ControlledConfirmDialog
        open={dialog?.kind === "delete"}
        onOpenChange={(open) => {
          if (!open) onClose();
        }}
        title={`Delete “${dialog?.title ?? "this chat"}”?`}
        description="The conversation and its saved state are removed. This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={onDelete}
      />
    </>
  );
}
