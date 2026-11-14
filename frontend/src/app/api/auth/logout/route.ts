import { cookies } from "next/headers";

import { SESSION_COOKIE } from "@/lib/auth/session";

/** Clear the session cookie. Logout is a cookie deletion, not a backend call. */
export async function POST() {
  const store = await cookies();
  store.delete(SESSION_COOKIE);

  return new Response(null, { status: 204 });
}
