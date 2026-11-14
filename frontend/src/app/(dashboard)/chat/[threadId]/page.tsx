import { ConversationView } from "@/features/chat/components/conversation-view";

/**
 * An existing conversation. `threadId` comes from the URL so the active thread
 * is shareable and survives a reload; a thread the caller does not own answers
 * 404 from the backend and is shown as "not found".
 */
export default async function ThreadPage({
  params,
}: {
  params: Promise<{ threadId: string }>;
}) {
  const { threadId } = await params;

  return <ConversationView threadId={decodeURIComponent(threadId)} />;
}
