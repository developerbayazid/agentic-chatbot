"use client";

import { useParams } from "next/navigation";

import { ConversationView } from "@/features/chat/components/conversation-view";

/**
 * The conversation route, for both a new chat and an existing thread.
 *
 * An **optional catch-all** segment, deliberately:
 *
 *  - `/chat` (new conversation) and `/chat/<id>` (existing) resolve to the *same*
 *    route and the same mounted component. Switching between them — which is what
 *    happens the moment a first message creates a thread — updates the URL
 *    without remounting, so the streamed reply survives instead of being thrown
 *    away and refetched.
 *  - The id is read with `useParams()` on the client. This was previously an
 *    `async` server component awaiting `params`, which forced a server round-trip
 *    before rendering and made every navigation a route fetch; Next reported it
 *    as "encountered URL data during prerendering or a navigation".
 *
 * The id stays in the URL, so a conversation remains shareable and survives a
 * reload. History itself is loaded by TanStack Query, which caches per thread.
 */
export default function ChatRoute() {
  const params = useParams<{ threadId?: string | string[] }>();
  const raw = params?.threadId;

  // Optional catch-all yields an array; it is briefly undefined while the router
  // settles, and a bare `/chat` has no segment at all.
  const encoded = Array.isArray(raw) ? raw[0] : raw;

  return (
    <ConversationView threadId={encoded ? decodeURIComponent(encoded) : null} />
  );
}
