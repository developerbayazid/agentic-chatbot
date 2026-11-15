"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { toast } from "sonner";

import {
  buildCommands,
  filterCommands,
  resolveCommand,
  splitCommand,
  type CommandContext,
  type CommandDefinition,
} from "@/features/commands/registry";
import {
  useDeleteThread,
  useRenameThread,
  useThreads,
} from "@/features/threads/hooks/use-threads";

export interface CommandDialogState {
  kind: "rename" | "delete";
  threadId: string;
  title: string;
}

/**
 * Binds the command registry to real application actions.
 *
 * Every handler routes through existing services (`ThreadService` via the REST
 * endpoints) or navigation. Nothing here touches a shell, and a planned command
 * only ever produces a message.
 */
export function useCommands(threadId: string | null, onMessage: (text: string) => void) {
  const router = useRouter();
  const threads = useThreads();
  const rename = useRenameThread();
  const remove = useDeleteThread();
  const [dialog, setDialog] = useState<CommandDialogState | null>(null);

  const currentTitle = useMemo(
    () => threads.data?.find((thread) => thread.thread_id === threadId)?.title ?? "this chat",
    [threads.data, threadId],
  );

  const commands = useMemo(
    () =>
      buildCommands({
        newChat: () => router.push("/chat"),
        openThreads: () => router.push("/chat"),
        showHistory: () => onMessage("Your conversation is right here — scroll to review it."),
        renameThread: () => {
          if (!threadId) {
            onMessage("There is no conversation to rename yet. Send a message first.");
            return;
          }
          setDialog({ kind: "rename", threadId, title: currentTitle });
        },
        deleteThread: () => {
          if (!threadId) {
            onMessage("There is no conversation to delete yet.");
            return;
          }
          setDialog({ kind: "delete", threadId, title: currentTitle });
        },
        openApprovals: () => router.push("/approvals"),
        openDocuments: () => router.push("/documents"),
        showHelp: () => onMessage("Use / to see every command."),
      }),
    [currentTitle, onMessage, router, threadId],
  );

  /** Execute a resolved command. Returns true when it consumed the input. */
  const run = useCallback(
    async (command: CommandDefinition) => {
      if (command.availability === "planned") {
        // Never fake success: the message is the whole result.
        onMessage(command.comingSoonMessage ?? "This feature is not available yet.");
        return;
      }

      try {
        await command.handler?.({ threadId } as CommandContext);
      } catch (error) {
        onMessage(
          error instanceof Error ? error.message : "That command could not run.",
        );
      }
    },
    [onMessage, threadId],
  );

  /**
   * Handle typed input. Returns true when the text was a slash command, so the
   * caller can skip sending it to the model.
   */
  const submit = useCallback(
    async (text: string): Promise<boolean> => {
      if (!text.trim().startsWith("/")) return false;

      const { command: name } = splitCommand(text);
      const command = resolveCommand(commands, name);

      if (!command) {
        onMessage(`Unknown command: ${name}. Type / to see what is available.`);
        return true;
      }

      await run(command);
      return true;
    },
    [commands, onMessage, run],
  );

  const confirmRename = useCallback(
    async (title: string) => {
      if (!dialog) return;

      try {
        await rename.mutateAsync({ threadId: dialog.threadId, title });
        toast.success("Conversation renamed.");
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Rename failed.");
      } finally {
        setDialog(null);
      }
    },
    [dialog, rename],
  );

  const confirmDelete = useCallback(async () => {
    if (!dialog) return;

    try {
      await remove.mutateAsync(dialog.threadId);
      toast.success("Conversation deleted.");
      setDialog(null);
      router.push("/chat");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Delete failed.");
    }
  }, [dialog, remove, router]);

  return {
    commands,
    filter: (query: string) => filterCommands(commands, query),
    submit,
    run,
    dialog,
    closeDialog: () => setDialog(null),
    confirmRename,
    confirmDelete,
    getDialog: () => dialog,
  };
}
