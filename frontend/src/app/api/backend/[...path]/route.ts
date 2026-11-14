import { cookies } from "next/headers";

import { backendBaseUrl, SESSION_COOKIE } from "@/lib/auth/session";

/**
 * Authenticated proxy to FastAPI.
 *
 *   browser → /api/backend/api/v1/... → BACKEND_API_URL/api/v1/...
 *
 * The bearer token is attached here from the HttpOnly cookie, so it never
 * exists in client JavaScript. The response body is passed through unbuffered,
 * which is what makes `text/event-stream` progressive.
 */

const FORWARDED_HEADERS = ["content-type", "accept"];

export async function GET(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  return forward(request, context);
}

export async function POST(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  return forward(request, context);
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  return forward(request, context);
}

export async function DELETE(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  return forward(request, context);
}

async function forward(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  const token = (await cookies()).get(SESSION_COOKIE)?.value;

  if (!token) {
    return unauthorized("A bearer token is required.");
  }

  const url = new URL(request.url);
  const target = `${backendBaseUrl()}/${path.join("/")}${url.search}`;

  const headers = new Headers({ authorization: `Bearer ${token}` });

  for (const name of FORWARDED_HEADERS) {
    const value = request.headers.get(name);

    if (value) {
      headers.set(name, value);
    }
  }

  const body =
    request.method === "GET" || request.method === "DELETE"
      ? undefined
      : await request.arrayBuffer();

  let upstream: Response;

  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      // Never follow redirects: a trailing-slash 307 would drop the
      // Authorization header and surface a misleading 401.
      redirect: "manual",
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

  const responseHeaders = new Headers();

  for (const name of [
    "content-type",
    "cache-control",
    "x-accel-buffering",
    "x-request-id",
    "www-authenticate",
  ]) {
    const value = upstream.headers.get(name);

    if (value) {
      responseHeaders.set(name, value);
    }
  }

  // Stream the body straight through; do not await .text().
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

function unauthorized(message: string): Response {
  return Response.json(
    {
      error: {
        code: "UNAUTHORIZED",
        message,
      },
    },
    { status: 401, headers: { "www-authenticate": "Bearer" } },
  );
}
