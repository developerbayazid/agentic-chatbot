import { ApiError, type ApiErrorBody } from "@/lib/api/errors";

/**
 * Every browser request goes through the Next.js BFF proxy, never directly to
 * FastAPI. The proxy attaches the bearer token from an HttpOnly cookie, so no
 * token is ever readable by client JavaScript.
 *
 *   browser → /api/backend/api/v1/threads → FastAPI
 */
export const PROXY_PREFIX = "/api/backend";

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  /** JSON body. Mutually exclusive with `form`. */
  json?: unknown;
  /** multipart/form-data body. */
  form?: FormData;
  signal?: AbortSignal;
  /** Extra headers, e.g. Accept for SSE. */
  headers?: Record<string, string>;
}

/** Called when the backend answers 401 so the app can clear its session. */
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${PROXY_PREFIX}${normalized}`;
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null;

  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    // A non-JSON failure (proxy timeout, HTML error page) keeps the status.
  }

  const code = body?.error?.code ?? `HTTP_${response.status}`;
  const message =
    body?.error?.message ??
    (response.status === 401
      ? "Your session has expired. Please sign in again."
      : response.statusText || "The request failed.");

  return new ApiError(response.status, code, message, body?.error?.request_id);
}

/**
 * Perform one request and decode the result.
 *
 * Errors, cancellation, and unauthorized responses are handled here so no
 * caller has to reimplement any of it.
 */
export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", json, form, signal, headers } = options;

  const init: RequestInit = { method, signal, headers: { ...headers } };

  if (json !== undefined) {
    init.body = JSON.stringify(json);
    init.headers = {
      "content-type": "application/json",
      ...init.headers,
    };
  } else if (form) {
    init.body = form;
  }

  let response: Response;

  try {
    response = await fetch(apiUrl(path), init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }

    throw new ApiError(
      0,
      "NETWORK_ERROR",
      "Cannot reach the server. Check that the backend is running.",
    );
  }

  if (response.status === 401) {
    onUnauthorized?.();
    throw await toApiError(response);
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

/**
 * Open a streaming request (SSE). Returns the raw Response so the caller can
 * read `body` incrementally; the caller owns the reader.
 */
export async function requestStream(
  path: string,
  options: RequestOptions = {},
): Promise<Response> {
  const { method = "POST", json, signal, headers } = options;

  const response = await fetch(apiUrl(path), {
    method,
    signal,
    headers: {
      accept: "text/event-stream",
      ...(json !== undefined ? { "content-type": "application/json" } : {}),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : undefined,
  });

  if (response.status === 401) {
    onUnauthorized?.();
    throw await toApiError(response);
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  return response;
}
