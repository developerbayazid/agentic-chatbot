"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

export interface ScrollMetrics {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
}

/**
 * Distance in pixels from the bottom of a scroll container.
 *
 * Kept as a pure function so the "should I follow?" decision is testable without
 * a real DOM and without layout timing.
 */
export function distanceFromBottom(metrics: ScrollMetrics): number {
  return metrics.scrollHeight - metrics.scrollTop - metrics.clientHeight;
}

/** True when the viewport is close enough to the bottom to follow new content. */
export function isNearBottom(metrics: ScrollMetrics, threshold = 80): boolean {
  return distanceFromBottom(metrics) <= threshold;
}

export interface StickToBottomOptions {
  /** How close to the bottom still counts as "following". */
  threshold?: number;
  /** Content that should pull the view down when the reader is following. */
  deps: unknown[];
}

/**
 * Keep a conversation pinned to its newest message without hijacking the reader.
 *
 * The rule is deliberately one-directional: we only scroll while the reader is
 * already at the bottom. Scrolling up detaches, and nothing yanks them back —
 * the UI offers a jump control instead.
 */
export function useStickToBottom({
  threshold = 80,
  deps,
}: StickToBottomOptions) {
  const ref = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);
  const [pinned, setPinned] = useState(true);
  /** Set when content arrives while the reader is scrolled away. */
  const [unseen, setUnseen] = useState(0);

  const read = useCallback((): ScrollMetrics | null => {
    const element = ref.current;
    if (!element) return null;

    return {
      scrollTop: element.scrollTop,
      scrollHeight: element.scrollHeight,
      clientHeight: element.clientHeight,
    };
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const element = ref.current;
    if (!element) return;

    element.scrollTo({ top: element.scrollHeight, behavior });
    pinnedRef.current = true;
    setPinned(true);
    setUnseen(0);
  }, []);

  // Track the reader's position. Passive so it never blocks scrolling.
  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    function onScroll() {
      const metrics = read();
      if (!metrics) return;

      const following = isNearBottom(metrics, threshold);
      pinnedRef.current = following;
      setPinned((previous) => (previous === following ? previous : following));

      if (following) setUnseen(0);
    }

    element.addEventListener("scroll", onScroll, { passive: true });
    return () => element.removeEventListener("scroll", onScroll);
  }, [read, threshold]);

  // Follow new content only while pinned. `useLayoutEffect` runs before paint,
  // so a streamed token lands at the bottom without a visible jump.
  useLayoutEffect(() => {
    if (!pinnedRef.current) {
      setUnseen((count) => count + 1);
      return;
    }

    const element = ref.current;
    if (element) element.scrollTop = element.scrollHeight;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { ref, pinned, unseen, scrollToBottom, read };
}

/**
 * Position a scroll container at its newest content immediately, with no
 * animation — used when a conversation opens, so the reader never sees it jump.
 */
export function jumpToBottom(element: HTMLDivElement | null): void {
  if (!element) return;
  element.scrollTop = element.scrollHeight;
}
