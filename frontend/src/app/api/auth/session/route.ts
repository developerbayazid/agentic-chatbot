import { cookies } from "next/headers";

import { isExpired, readSession, SESSION_COOKIE } from "@/lib/auth/session";

/** Report the current session to the client without exposing the token. */
export async function GET() {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = readSession(token);

  if (!session || isExpired(session)) {
    return Response.json({ authenticated: false }, { status: 200 });
  }

  return Response.json({
    authenticated: true,
    subject: session.subject,
    expiresAt: session.expiresAt,
  });
}
