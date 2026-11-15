"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { LogOut, Settings, User } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils/cn";
import { Button } from "@/components/ui/button";
import { useSession } from "@/features/auth/hooks/use-session";

/**
 * Account menu. There is deliberately no theme toggle: this phase ships one
 * designed theme, so a switch here would be a control that does nothing.
 */
export function AccountMenu({ collapsed }: { collapsed: boolean }) {
  const { subject, logout } = useSession();

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button
          variant="ghost"
          className={cn("min-w-0 flex-1 justify-start gap-2 px-1.5", collapsed && "md:flex-none")}
        >
          <span className="grid size-5 shrink-0 place-items-center rounded-full bg-surface-active">
            <User className="size-3" />
          </span>
          <span className={cn("truncate text-[12.5px] text-muted-strong", collapsed && "md:hidden")}>
            {subject ?? "Operator"}
          </span>
        </Button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={6}
          className="z-50 min-w-44 rounded-lg border border-border bg-surface-raised p-1 shadow-lg"
        >
          <DropdownMenu.Item asChild>
            <Link
              href="/settings"
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[13px] outline-none hover:bg-surface-hover"
            >
              <Settings className="size-3.5" />
              Settings
            </Link>
          </DropdownMenu.Item>

          <DropdownMenu.Separator className="my-1 h-px bg-border" />

          <DropdownMenu.Item
            className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-danger outline-none hover:bg-surface-hover"
            onSelect={() => void logout()}
          >
            <LogOut className="size-3.5" />
            Sign out
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
