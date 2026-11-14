import { ConversationView } from "@/features/chat/components/conversation-view";

/** A brand-new conversation. The thread is created by the first message. */
export default function NewChatPage() {
  return <ConversationView threadId={null} />;
}
