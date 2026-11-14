"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FileText,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  ShieldCheck,
  SquarePen,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils/cn";
import { Button } from "@/components/ui/button";
import { useUiStore } from "@/stores/ui";
import { ThreadList } from "@/features/threads/components/thread-list";
import { AccountMenu } from "@/components/layout/account-menu";

const NAV = [
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/approvals", label: "Approvals", icon: ShieldCheck },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * Warm-gray, compact sidebar. The conversation list gets the space; navigation
 * is a quiet footer of text rows rather than large cards.
 */
export function Sidebar() {
  const pathname = usePathname();
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const mobileOpen = useUiStore((s) => s.mobileNavOpen);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const setMobileNavOpen = useUiStore((s) => s.setMobileNavOpen);

  return (
    <>
      {mobileOpen && (
        <button
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-foreground/20 md:hidden"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      <aside
        aria-label="Primary"
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[17rem] flex-col bg-sidebar",
          "transition-transform duration-200 ease-out md:static md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          collapsed ? "md:w-14" : "md:w-[17rem]",
        )}
      >
        <div className="flex items-center justify-between px-3 pt-3 pb-1">
          <Link
            href="/chat"
            className={cn(
              "flex items-center gap-2 text-[15px] font-medium tracking-tight",
              collapsed && "md:hidden",
            )}
          >
            <span
              aria-hidden
              className="grid size-6 place-items-center rounded-md bg-accent text-[11px] font-bold text-accent-contrast"
            >
              B
            </span>
            BAYAZID AI
          </Link>

          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Close navigation"
            className="md:hidden"
            onClick={() => setMobileNavOpen(false)}
          >
            <X />
          </Button>
        </div>

        <div className={cn("px-2 pt-1", collapsed && "md:px-1.5")}>
          <Link
            href="/chat"
            onClick={() => setMobileNavOpen(false)}
            className={cn(
              "flex items-center gap-2 rounded-lg px-2 py-1.5 text-[13.5px] font-medium",
              "text-foreground transition-colors hover:bg-surface-hover",
              collapsed && "md:justify-center",
            )}
          >
            <SquarePen className="size-[15px] text-accent" />
            <span className={cn(collapsed && "md:hidden")}>New chat</span>
          </Link>
        </div>

        <div className={cn("mt-1 min-h-0 flex-1 overflow-hidden", collapsed && "md:hidden")}>
          <ThreadList />
        </div>

        <nav className={cn("mt-1 space-y-px px-2 pb-1", collapsed && "md:px-1.5")} aria-label="Sections">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setMobileNavOpen(false)}
              aria-current={isActive(pathname, href) ? "page" : undefined}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-1.5 text-[13.5px]",
                "text-muted-strong transition-colors hover:bg-surface-hover hover:text-foreground",
                isActive(pathname, href) && "bg-surface-hover text-foreground",
                collapsed && "md:justify-center",
              )}
            >
              <Icon className="size-[15px]" />
              <span className={cn(collapsed && "md:hidden")}>{label}</span>
            </Link>
          ))}
        </nav>

        <div className={cn("quiet-divider px-2 pb-2 pt-1.5", collapsed && "md:px-1.5")}>
          <div className={cn("flex items-center gap-1", collapsed && "md:flex-col")}>
            <AccountMenu collapsed={collapsed} />
            <Button
              variant="ghost"
              size="icon-sm"
              className="hidden md:inline-flex"
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              onClick={toggleSidebar}
            >
              {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            </Button>
          </div>
        </div>
      </aside>
    </>
  );
}
