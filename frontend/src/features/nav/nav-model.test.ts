import { describe, expect, it } from "vitest";

import { PLATFORM_NAV, WORKSPACE_NAV } from "@/features/nav/nav-model";

const ROUTES = [
  "/documents",
  "/approvals",
  "/tools",
  "/skills",
  "/plugins",
  "/mcp",
  "/settings",
];

describe("navigation model", () => {
  it("separates implemented features from planned ones", () => {
    const available = [...WORKSPACE_NAV].map((item) => item.href);

    expect(available).toEqual(["/documents", "/approvals", "/tools"]);
    expect(PLATFORM_NAV.every((item) => item.availability === "soon")).toBe(true);
  });

  it("labels every planned section as not yet available", () => {
    // A planned item without a blurb would render "Soon" with no explanation.
    for (const item of PLATFORM_NAV) {
      expect(item.blurb, `${item.label} needs an explanation`).toBeTruthy();
    }
  });

  it("does not present ERP management as a navigation section", () => {
    const labels = [...WORKSPACE_NAV, ...PLATFORM_NAV].map((item) =>
      item.label.toLowerCase(),
    );

    for (const forbidden of ["inventory", "erp", "products", "stock", "suppliers"]) {
      expect(labels).not.toContain(forbidden);
    }
  });

  it("has no duplicate destinations", () => {
    const hrefs = [...WORKSPACE_NAV, ...PLATFORM_NAV].map((item) => item.href);

    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("every navigation target is a known route", () => {
    for (const item of [...WORKSPACE_NAV, ...PLATFORM_NAV]) {
      expect(ROUTES).toContain(item.href);
    }
  });
});
