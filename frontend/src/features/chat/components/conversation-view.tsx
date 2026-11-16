"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Loader2, Terminal, X } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/errors";
import { useChatStream } from "@/features/chat/hooks/use-chat-stream";
import { jumpToBottom, useStickToBottom } from "@/features/chat/hooks/use-stick-to-bottom";
import { useThreadHistory } from "@/features/threads/hooks/use-threads";
import { ChatComposer } from "@/features/chat/components/chat-composer";
import {
  AssistantMessage,
  ToolLine,
  UserMessage,
} from "@/features/chat/components/message";
import { ToolActivityRow } from "@/features/chat/components/tool-activity";
import { WelcomeScreen } from "@/features/chat/components/welcome-screen";
import { JumpToLatest } from "@/features/chat/components/jump-to-latest";
import { ApprovalPrompt } from "@/features/approvals/components/approval-prompt";
import { useApproval } from "@/features/approvals/hooks/use-approvals";
import { useCommands } from "@/features/commands/hooks/use-commands";
import { CommandDialogs } from "@/features/commands/components/command-dialogs";

/**
 * One conversation.
 *
 * Restored turns come from the checkpoint-backed history endpoint; the live turn
 * comes from the SSE stream. A pending approval is read from the approvals
 * endpoint rather than inferred from a stream we may not have seen.
 *
 * Scrolling follows one rule: open at the newest message, keep following while
 * the reader is at the bottom, and stop the moment they scroll away.
 */
export function ConversationView({ threadId }: { threadId: string | null }) {
  const router = useRouter();
  const history = useThreadHistory(threadId);
  const stream = useChatStream();
  const approval = useApproval(threadId);
  const [draft, setDraft] = useState("");

  const restored = history.data?.messages ?? [];
  const streaming = stream.status === "streaming";
  const awaiting = approval.data?.approval_id ?? stream.approvalId;
  const emptyTurn =
    restored.length === 0 && !stream.text && stream.tools.length === 0;

  const { ref: scrollRef, pinned, unseen, scrollToBottom } = useStickToBottom({
    deps: [restored.length, stream.text, stream.status, stream.tools.length, awaiting],
  });

  // Command output is shown as an assistant-style notice, clearly marked as a
  // local message rather than model output.
  const [notice, setNotice] = useState<string | null>(null);
  const commands = useCommands(threadId, setNotice);

  // Opening a conversation should land on its newest message with no animation.
  // `history.dataUpdatedAt` changes on every successful fetch, so this re-runs
  // when a different thread's messages arrive.
  const openedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!history.data || openedFor.current === history.data.thread_id) return;

    openedFor.current = history.data.thread_id;
    jumpToBottom(scrollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history.data]);

  async function send(message: string) {
    setDraft("");

    // A slash command never reaches the model.
    if (await commands.submit(message)) return;

    scrollToBottom("auto");
    const resolved = await stream.send(message, threadId);

    if (!threadId && resolved) {
      router.replace(`/chat/${encodeURIComponent(resolved)}`);
    }
  }

  return (
    // `h-full` fills the scrolling `main` without adding a second scrollbar;
    // the conversation owns its own scroll container so the composer stays put.
    <div className="flex h-full flex-col">
      <div className="relative min-h-0 flex-1">
        <div ref={scrollRef} className="scroll-area h-full overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl px-5 pb-10 pt-6">
            {history.isLoading && threadId && (
              <div className="space-y-3">
                <Skeleton className="h-11 w-2/3" />
                <Skeleton className="h-16 w-full" />
              </div>
            )}

            {history.isError && (
              <div className="flex items-start gap-2 rounded-card border border-danger/25 bg-danger-soft p-3 text-[13px]">
                <AlertCircle className="mt-0.5 size-4 text-danger" />
                <div>
                  <p className="text-danger">Could not load this conversation.</p>
                  <p className="mt-1 text-muted">{errorMessage(history.error)}</p>
                </div>
              </div>
            )}

            {emptyTurn && !threadId && (
              <WelcomeScreen onPick={(prompt) => setDraft(prompt)} />
            )}

            {emptyTurn && threadId && !history.isLoading && !history.isError && (
              <div className="py-20 text-center">
                <h2 className="text-[17px] font-medium">Continue where you left off</h2>
                <p className="mt-1.5 text-[13.5px] text-muted">
                  This conversation has no saved messages yet.
                </p>
              </div>
            )}

            {restored.length > 0 && (
              <div className="space-y-6">
                {restored.map((message, index) =>
                  message.role === "user" ? (
                    <UserMessage key={index} content={message.content} />
                  ) : message.role === "assistant" ? (
                    <AssistantMessage key={index} content={message.content} />
                  ) : (
                    <ToolLine key={index} content={message.content} />
                  ),
                )}
              </div>
            )}

            {/* The live turn: tool activity first, then the answer, in the order
                the backend emitted them. */}
            {(stream.text || stream.tools.length > 0 || streaming) && (
              <div className="mt-6 space-y-2.5">
                {stream.tools.map((tool) => (
                  <ToolActivityRow key={tool.callId} activity={tool} />
                ))}

                {stream.text && (
                  <AssistantMessage content={stream.text} streaming={streaming} />
                )}

                {streaming && !stream.text && stream.tools.length === 0 && (
                  <p className="flex items-center gap-2 text-[13px] text-muted">
                    <Loader2 className="size-3.5 animate-spin" /> Thinking…
                  </p>
                )}
              </div>
            )}

            {stream.status === "error" && stream.error && (
              <div className="mt-4 flex items-start gap-2 rounded-card border border-danger/25 bg-danger-soft p-3 text-[13px]">
                <AlertCircle className="mt-0.5 size-4 text-danger" />
                <div>
                  <p className="text-danger">{stream.error}</p>
                  <p className="mt-1 text-muted">
                    Your conversation is unchanged. Try sending again.
                  </p>
                </div>
              </div>
            )}

            {stream.status === "stopped" && (
              <p className="mt-3 text-[12px] text-muted">
                You stopped this response, so it may be incomplete.
              </p>
            )}

            {notice && (
              <div
                role="status"
                className="mt-4 flex items-start gap-2 rounded-card border border-border bg-surface p-3 text-[13px]"
              >
                <Terminal className="mt-0.5 size-3.5 shrink-0 text-muted" />
                <p className="flex-1 text-muted-strong">{notice}</p>
                <button
                  type="button"
                  onClick={() => setNotice(null)}
                  aria-label="Dismiss"
                  className="text-muted transition-colors hover:text-foreground"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            )}

            {awaiting && approval.data && (
              <div className="mt-4">
                <ApprovalPrompt
                  approval={approval.data}
                  onDecided={() => {
                    void history.refetch();
                    void approval.refetch();
                  }}
                />
              </div>
            )}
          </div>
        </div>

        <JumpToLatest
          visible={!pinned && (streaming || unseen > 0)}
          unseen={unseen}
          onClick={() => scrollToBottom()}
        />
      </div>

      <ChatComposer
        value={draft}
        onChange={setDraft}
        onSend={(message) => void send(message)}
        onStop={stream.stop}
        onCommand={(command) => void commands.run(command)}
        filterCommands={commands.filter}
        streaming={streaming}
        disabled={Boolean(awaiting)}
        placeholder={
          awaiting
            ? "Decide the pending action to continue…"
            : "How can I help you today?"
        }
      />

      <CommandDialogs
        dialog={commands.dialog}
        onClose={commands.closeDialog}
        onRename={(title) => void commands.confirmRename(title)}
        onDelete={() => void commands.confirmDelete()}
      />
    </div>
  );
}
