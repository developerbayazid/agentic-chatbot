/**
 * The backend's error envelope. Every FastAPI failure returns this shape:
 *
 *   { "error": { "code": "THREAD_NOT_FOUND", "message": "...", "request_id": "..." } }
 *
 * `code` is the machine-readable discriminator; `message` is already written
 * for a human, so the UI can show it verbatim rather than inventing text.
 */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id?: string;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(
    status: number,
    code: string,
    message: string,
    requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }

  /** Session is gone: re-authenticate rather than show a generic failure. */
  get isUnauthorized() {
    return this.status === 401;
  }

  static isApiError(error: unknown): error is ApiError {
    return error instanceof ApiError;
  }
}

/** Human-readable text for any thrown value, without leaking internals. */
export function errorMessage(error: unknown): string {
  if (ApiError.isApiError(error)) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong. Please try again.";
}

export function isAbortError(error: unknown): boolean {
  return (
    error instanceof DOMException
      ? error.name === "AbortError"
      : error instanceof Error && error.name === "AbortError"
  );
}
