"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { LogOut, Moon, Sun, User } from "lucide-react";
import { useTheme } from "next-themes";

import { cn } from "@/lib/utils/cn";
import { Button } from "@/components/ui/button";
import { useSession } from "@/features/auth/hooks/use-session";

export function AccountMenu({ collapsed }: { collapsed: boolean }) {
  const { subject, logout } = useSession();
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button
          variant="ghost"
          className={cn("min-w-0 flex-1 justify-start gap-2 px-1.5", collapsed && "md:flex-none")}
        >
          <span className="grid size-5 shrink-0 place-items-center rounded-full bg-surface-hover">
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
          <DropdownMenu.Item
            className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[13px] outline-none hover:bg-surface-hover"
            onSelect={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          >
            {resolvedTheme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
            {resolvedTheme === "dark" ? "Light theme" : "Dark theme"}
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
