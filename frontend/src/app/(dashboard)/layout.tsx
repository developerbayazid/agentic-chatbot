import { Suspense } from "react";

import { AppShell } from "@/components/layout/app-shell";

/**
 * The authenticated application. Route protection itself lives in
 * `middleware.ts` so an unauthenticated request never renders this shell.
 *
 * `<Suspense>` is required: the sidebar reads `usePathname()`, which is only
 * available at runtime and would otherwise block prerendering.
 */
export default function DashboardLayout({ children }: LayoutProps<"/">) {
  return (
    <Suspense>
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
