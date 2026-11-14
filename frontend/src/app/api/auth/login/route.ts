import { cookies } from "next/headers";

import { backendBaseUrl, isExpired, readSession, secureCookie, SESSION_COOKIE } from "@/lib/auth/session";

/**
 * Exchange an API key for a JWT and keep it in an HttpOnly cookie.
 *
 * The token is returned by FastAPI and immediately written server-side; the
 * response to the browser contains only the subject, never the credential.
 */
export async function POST(request: Request) {
  let apiKey: unknown;

  try {
    ({ api_key: apiKey } = (await request.json()) as { api_key?: unknown });
  } catch {
    return badRequest("Send a JSON body with an api_key.");
  }

  if (typeof apiKey !== "string" || apiKey.trim().length === 0) {
    return badRequest("An API key is required.");
  }

  let upstream: Response;

  try {
    upstream = await fetch(`${backendBaseUrl()}/api/v1/auth/token`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ api_key: apiKey.trim() }),
    });
  } catch {
    return Response.json(
      {
        error: {
          code: "BACKEND_UNREACHABLE",
          message: "Cannot reach the BAYAZID AI backend. Is it running?",
        },
      },
      { status: 502 },
    );
  }

  if (!upstream.ok) {
    // Pass the backend's own envelope through: its message is already
    // user-facing and names the real cause.
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "content-type": "application/json" },
    });
  }

  const { access_token: token } = (await upstream.json()) as {
    access_token?: string;
  };
  const session = readSession(token);

  if (!token || !session || isExpired(session)) {
    return Response.json(
      {
        error: {
          code: "INVALID_CREDENTIALS",
          message: "The backend returned an unusable token.",
        },
      },
      { status: 502 },
    );
  }

  const store = await cookies();
  store.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: secureCookie(),
    path: "/",
    expires: new Date(session.expiresAt * 1000),
  });

  return Response.json({
    authenticated: true,
    subject: session.subject,
    expiresAt: session.expiresAt,
  });
}

function badRequest(message: string): Response {
  return Response.json(
    { error: { code: "VALIDATION_ERROR", message } },
    { status: 422 },
  );
}
