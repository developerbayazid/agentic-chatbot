/**
 * Server-only helpers for the BFF session.
 *
 * The JWT lives in an HttpOnly cookie: the browser sends it automatically, JS
 * cannot read it, and the proxy is the only thing that turns it into an
 * `Authorization` header. Nothing here is importable from client components
 * (no "use client", and `next/headers` is server-only).
 */

export const SESSION_COOKIE = "bayazid_session";

export interface SessionInfo {
  subject: string;
  expiresAt: number;
}

/**
 * Decode the JWT payload without verifying the signature.
 *
 * Verification is the backend's job: every request the proxy forwards is
 * re-validated there. This exists only to render the account label and to
 * decide whether the cookie is worth sending at all — never as a security
 * boundary. A forged cookie simply gets 401 from FastAPI.
 */
export function readSession(token: string | undefined): SessionInfo | null {
  if (!token) {
    return null;
  }

  const parts = token.split(".");

  if (parts.length !== 3) {
    return null;
  }

  try {
    const payload = JSON.parse(
      Buffer.from(parts[1], "base64url").toString("utf8"),
    ) as { sub?: unknown; exp?: unknown };

    if (typeof payload.sub !== "string" || typeof payload.exp !== "number") {
      return null;
    }

    return { subject: payload.sub, expiresAt: payload.exp };
  } catch {
    return null;
  }
}

export function isExpired(session: SessionInfo | null): boolean {
  return session === null || session.expiresAt * 1000 <= Date.now();
}

/** The backend base URL. Server-only; never a NEXT_PUBLIC_ value. */
export function backendBaseUrl(): string {
  const url = readEnv("BACKEND_API_URL") ?? "http://127.0.0.1:8000";
  return url.replace(/\/+$/, "");
}

/**
 * Whether the session cookie is `Secure`.
 *
 * Tying this to `NODE_ENV=production` looks right but breaks a plain-HTTP
 * deployment: a browser (correctly) refuses to send a Secure cookie over
 * `http://`, so the session silently never authenticates. It is opt-in instead,
 * and defaults to on in production because that is the safe posture — set
 * `SESSION_COOKIE_SECURE=false` only for a deliberate HTTP-only deployment.
 */
export function secureCookie(): boolean {
  // Read at request time, not build time. Next inlines statically-analysable
  // `process.env.X` references into the bundle, which would freeze this to
  // whatever the build machine had. A trailing NODE_ENV guard keeps the safe
  // default: Secure everywhere except deliberate local development.
  const configured = readEnv("SESSION_COOKIE_SECURE")?.trim().toLowerCase();

  if (configured === "false" || configured === "0" || configured === "no") {
    return false;
  }

  if (configured === "true" || configured === "1" || configured === "yes") {
    return true;
  }

  return process.env.NODE_ENV === "production";
}

/**
 * Dynamic `process.env` lookup.
 *
 * Written with a variable key so Next's build-time replacement does not apply;
 * environment policy belongs to the running server, not the build.
 */
export function readEnv(name: string): string | undefined {
  const environment = process.env as Record<string, string | undefined>;

  return environment[name];
}
