"use client";

import { useState } from "react";
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

import { Button } from "@/components/ui/button";
import { ControlledConfirmDialog } from "@/components/ui/confirm-dialog";
import { errorMessage } from "@/lib/api/errors";
import { useDeleteThread, useRenameThread } from "@/features/threads/hooks/use-threads";

/**
 * Quiet row menu for one conversation: rename (PATCH) and delete (DELETE).
 * Deleting removes the checkpoints and the metadata server-side.
 */
export function ThreadRowMenu({
  threadId,
  title,
  onDeleted,
}: {
  threadId: string;
  title: string;
  onDeleted?: () => void;
}) {
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [draft, setDraft] = useState(title);
  const [error, setError] = useState<string | null>(null);
  const rename = useRenameThread();
  const remove = useDeleteThread();

  async function confirmDelete() {
    try {
      await remove.mutateAsync(threadId);
      onDeleted?.();
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }

  async function submitRename() {
    const next = draft.trim();

    if (!next || next.length > 100) {
      setError("A title needs 1–100 characters.");
      return;
    }

    try {
      await rename.mutateAsync({ threadId, title: next });
      setRenaming(false);
      setError(null);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }

  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${title}`}>
            <MoreHorizontal className="size-3.5" />
          </Button>
        </DropdownMenu.Trigger>

        <DropdownMenu.Portal>
          <DropdownMenu.Content
            sideOffset={4}
            className="z-50 min-w-36 rounded-lg border border-border bg-surface-raised p-1 shadow-lg"
          >
            <DropdownMenu.Item
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[13px] outline-none hover:bg-surface-hover"
              onSelect={() => {
                setDraft(title);
                setRenaming(true);
              }}
            >
              <Pencil className="size-3.5" /> Rename
            </DropdownMenu.Item>
            <DropdownMenu.Item
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-danger outline-none hover:bg-surface-hover"
              onSelect={() => setDeleting(true)}
            >
              <Trash2 className="size-3.5" /> Delete
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      {/* Rename prompt: a small inline dialog keeps the sidebar row intact. */}
      {renaming && (
        <ControlledConfirmDialog
          open={renaming}
          onOpenChange={setRenaming}
          title="Rename chat"
          description="A short title, 1–100 characters."
          confirmLabel="Save"
          input={{ value: draft, onChange: setDraft, maxLength: 100 }}
          onConfirm={() => void submitRename()}
        />
      )}

      {error && <p className="px-1 text-[11px] text-danger">{error}</p>}

      <ControlledConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete “${title}”?`}
        description="The conversation and its saved state are removed. This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={() => void confirmDelete()}
      />
    </>
  );
}
