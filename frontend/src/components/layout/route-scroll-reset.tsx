"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

/**
 * Single-page navigation behaviour.
 *
 * Next's App Router already swaps routes without a document load, so the app is
 * a SPA in the meaningful sense: one HTML document, one websocket-free session,
 * no full reload between pages. What it does *not* do by itself is reset the
 * scroll position of the shell's scrolling container — without this, navigating
 * from a long page (the tool catalog) to a short one leaves the reader stranded
 * part-way down a page that is now short.
 *
 * This resets only the shell's own scroller, never an inner conversation
 * scroller, so the chat view keeps its own position.
 */
export function RouteScrollReset() {
  const pathname = usePathname();

  useEffect(() => {
    const container = document.getElementById("main-scroll");

    if (container) {
      container.scrollTop = 0;
    }
  }, [pathname]);

  return null;
}
