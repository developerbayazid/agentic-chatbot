"use client";

import { Menu } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sidebar } from "@/components/layout/sidebar";
import { useUiStore } from "@/stores/ui";

/**
 * Application shell: sidebar plus the routed page.
 *
 * The shell is mounted once and never unmounts during navigation, which is what
 * makes the app feel like a single page: the sidebar, its scroll position, and
 * the open conversation list all survive a route change.
 *
 * Scrolling is owned here rather than by each page. `main` scrolls, so any page
 * longer than the viewport works without opting in — previously it was
 * `overflow-hidden`, which silently clipped long pages such as the tool catalog.
 * The conversation opts out of page scrolling by filling its own height, since
 * it manages a sticky composer and a scroll container internally.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const setMobileNavOpen = useUiStore((s) => s.setMobileNavOpen);

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      <Sidebar />

      <div className="relative flex min-w-0 flex-1 flex-col">
        {/* Mobile-only affordance: the conversation has no chrome on desktop. */}
        <div className="absolute left-3 top-3 z-20 md:hidden">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Open navigation"
            onClick={() => setMobileNavOpen(true)}
          >
            <Menu />
          </Button>
        </div>

        <main id="main-scroll" className="scroll-area min-h-0 flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
