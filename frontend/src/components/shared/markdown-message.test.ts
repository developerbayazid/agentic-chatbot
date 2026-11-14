import { describe, expect, it } from "vitest";

import { sanitizeHref } from "@/components/shared/markdown-message";

describe("sanitizeHref (markdown link safety)", () => {
  it("allows http and https", () => {
    expect(sanitizeHref("https://example.com")).toBe("https://example.com");
    expect(sanitizeHref("http://example.com")).toBe("http://example.com");
  });

  it("allows mailto", () => {
    expect(sanitizeHref("mailto:a@example.com")).toBe("mailto:a@example.com");
  });

  it("allows same-origin relative links and fragments", () => {
    expect(sanitizeHref("/chat/123")).toBe("/chat/123");
    expect(sanitizeHref("#section")).toBe("#section");
  });

  it("rejects javascript: and data: URLs", () => {
    expect(sanitizeHref("javascript:alert(1)")).toBeNull();
    expect(sanitizeHref("JavaScript:alert(1)")).toBeNull();
    expect(sanitizeHref("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(sanitizeHref("vbscript:msgbox(1)")).toBeNull();
  });

  it("rejects empty and missing hrefs", () => {
    expect(sanitizeHref(undefined)).toBeNull();
    expect(sanitizeHref("")).toBeNull();
    expect(sanitizeHref("   ")).toBeNull();
  });
});
