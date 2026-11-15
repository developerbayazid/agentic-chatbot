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

  it("recognises a no-longer-actionable approval", () => {
    expect(new ApiError(409, "APPROVAL_STALE", "changed").isStaleApproval).toBe(true);
    expect(
      new ApiError(409, "APPROVAL_NOT_PENDING", "none").isStaleApproval,
    ).toBe(true);
  });

  it("does not treat other conflicts as a stale approval", () => {
    // A conflict from a different feature must not dismiss the approval panel.
    expect(new ApiError(409, "THREAD_CONFLICT", "busy").isStaleApproval).toBe(false);
    expect(new ApiError(500, "APPROVAL_STALE", "weird").isStaleApproval).toBe(false);
    expect(new ApiError(404, "APPROVAL_NOT_FOUND", "gone").isStaleApproval).toBe(false);
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
