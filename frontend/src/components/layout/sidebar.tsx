"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelLeftClose, PanelLeftOpen, SquarePen, X } from "lucide-react";

import { cn } from "@/lib/utils/cn";
import { Button } from "@/components/ui/button";
import { useUiStore } from "@/stores/ui";
import { ThreadList } from "@/features/threads/components/thread-list";
import { AccountMenu } from "@/components/layout/account-menu";
import {
  PLATFORM_NAV,
  WORKSPACE_NAV,
  type NavItem,
} from "@/features/nav/nav-model";

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavRow({
  item,
  active,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  collapsed: boolean;
  onNavigate: () => void;
}) {
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      title={collapsed ? item.label : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] transition-colors",
        "text-muted-strong hover:bg-surface-hover hover:text-foreground",
        active && "bg-surface-active text-foreground",
        collapsed && "md:justify-center md:px-0",
      )}
    >
      <Icon className="size-4 shrink-0" />
      <span className={cn("truncate", collapsed && "md:hidden")}>{item.label}</span>
      {item.availability === "soon" && (
        <span
          className={cn(
            "ml-auto rounded px-1 py-px text-[10px] font-medium uppercase tracking-wide",
            "text-muted ring-1 ring-inset ring-border-strong",
            collapsed && "md:hidden",
          )}
        >
          Soon
        </span>
      )}
    </Link>
  );
}

/**
 * ChatGPT-style sidebar: actions at the top, grouped recents in the middle,
 * workspace and planned features below, account pinned at the bottom.
 *
 * Planned sections are visible on purpose — the product's direction is part of
 * the interface — but each is labelled "Soon" and leads to a page that says so
 * plainly. Nothing here implies a capability already exists.
 */
export function Sidebar() {
  const pathname = usePathname();
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const mobileOpen = useUiStore((s) => s.mobileNavOpen);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const setMobileNavOpen = useUiStore((s) => s.setMobileNavOpen);
  const close = () => setMobileNavOpen(false);

  return (
    <>
      {mobileOpen && (
        <button
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-foreground/20 md:hidden"
          onClick={close}
        />
      )}

      <aside
        aria-label="Primary"
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[16.5rem] flex-col border-r border-border bg-sidebar",
          "transition-transform duration-200 ease-out md:static md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          collapsed ? "md:w-14" : "md:w-[16.5rem]",
        )}
      >
        <div
          className={cn(
            "flex items-center justify-between px-3 py-3",
            collapsed && "md:justify-center md:px-0",
          )}
        >
          <Link
            href="/chat"
            className={cn(
              "flex items-center gap-2 text-[14px] font-semibold tracking-tight",
              collapsed && "md:hidden",
            )}
          >
            <span
              aria-hidden
              className="grid size-6 place-items-center rounded-md bg-foreground text-[11px] font-bold text-background"
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
            onClick={close}
          >
            <X />
          </Button>
        </div>

        {/* Primary action */}
        <div className={cn("px-2", collapsed && "md:px-1.5")}>
          <Link
            href="/chat"
            onClick={close}
            title={collapsed ? "New chat" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-lg border border-border-strong bg-background px-2.5 py-2",
              "text-[13.5px] font-medium text-foreground transition-colors hover:bg-surface-hover",
              collapsed && "md:justify-center md:px-0",
            )}
          >
            <SquarePen className="size-4 shrink-0" />
            <span className={cn(collapsed && "md:hidden")}>New chat</span>
          </Link>
        </div>

        {/* Recents */}
        <div
          className={cn(
            "mt-2 min-h-0 flex-1 overflow-hidden",
            collapsed && "md:hidden",
          )}
        >
          <ThreadList />
        </div>

        {/* Workspace + planned features */}
        <nav
          aria-label="Sections"
          className={cn(
            "mt-1 space-y-0.5 border-t border-border px-2 pt-2",
            collapsed && "md:px-1.5",
          )}
        >
          {!collapsed && (
            <p className="px-2.5 pb-1 text-[10.5px] font-medium uppercase tracking-[0.07em] text-muted">
              Workspace
            </p>
          )}
          {WORKSPACE_NAV.map((item) => (
            <NavRow
              key={item.href}
              item={item}
              active={isActive(pathname, item.href)}
              collapsed={collapsed}
              onNavigate={close}
            />
          ))}
          {PLATFORM_NAV.map((item) => (
            <NavRow
              key={item.href}
              item={item}
              active={isActive(pathname, item.href)}
              collapsed={collapsed}
              onNavigate={close}
            />
          ))}
        </nav>

        {/* Account */}
        <div
          className={cn(
            "mt-1 flex items-center gap-1 border-t border-border px-2 py-2",
            collapsed && "md:flex-col md:px-1.5",
          )}
        >
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
      </aside>
    </>
  );
}
