import { describe, expect, it } from "vitest";

import { coerce } from "@/features/approvals/components/approval-prompt";

describe("coerce (approval field editing)", () => {
  it("converts integer fields", () => {
    expect(coerce("95000", "integer", undefined)).toBe(95000);
  });

  it("keeps unparsable integers as text so the backend can reject them", () => {
    expect(coerce("abc", "integer", undefined)).toBe("abc");
  });

  it("converts numbers and preserves fractions", () => {
    expect(coerce("1.5", "number", undefined)).toBe(1.5);
  });

  it("converts booleans", () => {
    expect(coerce("true", "boolean", undefined)).toBe(true);
    expect(coerce("no", "boolean", undefined)).toBe(false);
  });

  it("parses arrays and objects as JSON", () => {
    expect(coerce('["a","b"]', "array", undefined)).toEqual(["a", "b"]);
    expect(coerce('{"k":1}', "object", undefined)).toEqual({ k: 1 });
  });

  it("returns raw text when a JSON field is invalid", () => {
    expect(coerce("{oops", "object", undefined)).toBe("{oops");
  });

  it("infers numbers from the current value when no type is declared", () => {
    expect(coerce("42", undefined, 1)).toBe(42);
  });

  it("leaves strings alone", () => {
    expect(coerce("PRD-1001", "string", "x")).toBe("PRD-1001");
  });
});
