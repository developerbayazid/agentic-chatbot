import { describe, expect, it } from "vitest";

import {
  distanceFromBottom,
  isNearBottom,
} from "@/features/chat/hooks/use-stick-to-bottom";

const metrics = (scrollTop: number, scrollHeight = 1000, clientHeight = 400) => ({
  scrollTop,
  scrollHeight,
  clientHeight,
});

describe("distanceFromBottom", () => {
  it("is zero when scrolled fully to the bottom", () => {
    expect(distanceFromBottom(metrics(600))).toBe(0);
  });

  it("grows as the reader scrolls up", () => {
    expect(distanceFromBottom(metrics(500))).toBe(100);
    expect(distanceFromBottom(metrics(0))).toBe(600);
  });

  it("is exact for a short page that does not scroll", () => {
    expect(distanceFromBottom(metrics(0, 300, 400))).toBe(-100);
  });
});

describe("isNearBottom", () => {
  it("follows when the reader is at or near the bottom", () => {
    expect(isNearBottom(metrics(600))).toBe(true);
    expect(isNearBottom(metrics(590))).toBe(true); // 10px away
    expect(isNearBottom(metrics(520))).toBe(true); // 80px, the threshold
  });

  it("detaches once the reader scrolls away", () => {
    expect(isNearBottom(metrics(519))).toBe(false); // 81px
    expect(isNearBottom(metrics(300))).toBe(false);
    expect(isNearBottom(metrics(0))).toBe(false);
  });

  it("honours a custom threshold", () => {
    expect(isNearBottom(metrics(500), 100)).toBe(true); // 100px
    expect(isNearBottom(metrics(499), 100)).toBe(false); // 101px
  });

  it("treats an unscrollable page as pinned", () => {
    // Content shorter than the viewport: there is nowhere to scroll away to.
    expect(isNearBottom(metrics(0, 300, 400))).toBe(true);
  });
});
