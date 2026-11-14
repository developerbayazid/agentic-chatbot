"use client";

import { Menu } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sidebar } from "@/components/layout/sidebar";
import { useUiStore } from "@/stores/ui";

/**
 * Application shell: warm sidebar + the conversation. There is deliberately no
 * top navigation bar over the content — the conversation owns the page.
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

        <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
