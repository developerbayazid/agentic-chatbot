"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Loader2 } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/errors";
import { useChatStream } from "@/features/chat/hooks/use-chat-stream";
import { useThreadHistory } from "@/features/threads/hooks/use-threads";
import { ChatComposer } from "@/features/chat/components/chat-composer";
import { AssistantMessage, UserMessage } from "@/features/chat/components/message";
import { ToolActivityRow } from "@/features/chat/components/tool-activity";
import { WelcomeScreen } from "@/features/chat/components/welcome-screen";
import { ApprovalPrompt } from "@/features/approvals/components/approval-prompt";
import { useApproval } from "@/features/approvals/hooks/use-approvals";

/**
 * One conversation.
 *
 * Restored turns come from the checkpoint-backed history endpoint; the live turn
 * comes from the SSE stream. A pending approval is read from the approvals
 * endpoint rather than inferred from a stream we may not have seen.
 */
export function ConversationView({ threadId }: { threadId: string | null }) {
  const router = useRouter();
  const history = useThreadHistory(threadId);
  const stream = useChatStream();
  const approval = useApproval(threadId);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState("");

  const restored = history.data?.messages ?? [];
  const streaming = stream.status === "streaming";
  const awaiting = approval.data?.approval_id ?? stream.approvalId;
  const emptyTurn =
    restored.length === 0 && !stream.text && stream.tools.length === 0;

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;

    const nearBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight < 180;

    if (nearBottom) element.scrollTop = element.scrollHeight;
  }, [restored.length, stream.text, stream.status, stream.tools.length]);

  async function send(message: string) {
    setDraft("");
    const resolved = await stream.send(message, threadId);

    if (!threadId && resolved) {
      router.replace(`/chat/${encodeURIComponent(resolved)}`);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-5 pb-8 pt-6">
          {history.isLoading && threadId && (
            <div className="space-y-3">
              <Skeleton className="h-11 w-2/3" />
              <Skeleton className="h-16 w-full" />
            </div>
          )}

          {history.isError && (
            <div className="flex items-start gap-2 rounded-xl border border-danger/25 bg-danger-soft p-3 text-[13px]">
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
              {restored.map((message, index) => {
                if (message.role === "user") {
                  return <UserMessage key={index} content={message.content} />;
                }

                if (message.role === "assistant") {
                  return <AssistantMessage key={index} content={message.content} />;
                }

                return (
                  <p key={index} className="font-mono text-[11.5px] text-muted">
                    {message.content}
                  </p>
                );
              })}
            </div>
          )}

          {/* The live turn: tool activity first, then the answer, as the backend
              emitted them. */}
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
            <div className="mt-4 flex items-start gap-2 rounded-xl border border-danger/25 bg-danger-soft p-3 text-[13px]">
              <AlertCircle className="mt-0.5 size-4 text-danger" />
              <div>
                <p className="text-danger">{stream.error}</p>
                <p className="mt-1 text-muted">
                  Your conversation is unchanged. Try sending again.
                </p>
              </div>
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

      <ChatComposer
        value={draft}
        onChange={setDraft}
        onSend={(message) => void send(message)}
        onStop={stream.stop}
        streaming={streaming}
        disabled={Boolean(awaiting)}
        placeholder={
          awaiting
            ? "Decide the pending action to continue…"
            : "How can I help you today?"
        }
      />
    </div>
  );
}
