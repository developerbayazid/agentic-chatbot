import { describe, expect, it } from "vitest";

import { ApiError, errorMessage, isAbortError } from "@/lib/api/errors";

describe("ApiError", () => {
  it("carries the backend's code, message, and request id", () => {
    const error = new ApiError(404, "THREAD_NOT_FOUND", "Not found.", "req-1");

    expect(error.status).toBe(404);
    expect(error.code).toBe("THREAD_NOT_FOUND");
    expect(error.message).toBe("Not found.");
    expect(error.requestId).toBe("req-1");
  });

  it("recognises a 401 as an auth problem", () => {
    expect(new ApiError(401, "UNAUTHORIZED", "no").isUnauthorized).toBe(true);
    expect(new ApiError(500, "INTERNAL_ERROR", "no").isUnauthorized).toBe(false);
  });
});

describe("errorMessage", () => {
  it("shows the backend's own message verbatim", () => {
    expect(
      errorMessage(new ApiError(409, "APPROVAL_STALE", "This approval changed.")),
    ).toBe("This approval changed.");
  });

  it("falls back for a plain Error", () => {
    expect(errorMessage(new Error("boom"))).toBe("boom");
  });

  it("falls back for an unknown value", () => {
    expect(errorMessage({ weird: true })).toBe(
      "Something went wrong. Please try again.",
    );
  });
});

describe("isAbortError", () => {
  it("recognises a cancelled request", () => {
    expect(isAbortError(new DOMException("aborted", "AbortError"))).toBe(true);
  });

  it("does not treat a real failure as a cancellation", () => {
    expect(isAbortError(new Error("network"))).toBe(false);
  });
});
