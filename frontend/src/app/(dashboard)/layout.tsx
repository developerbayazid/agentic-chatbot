import { Suspense } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { RouteScrollReset } from "@/components/layout/route-scroll-reset";

/**
 * The authenticated application. Route protection itself lives in
 * `middleware.ts` so an unauthenticated request never renders this shell.
 *
 * The shell is mounted once for every authenticated route, so navigating between
 * pages replaces only `children` — the sidebar and its state persist, which is
 * what makes this a single-page app rather than a series of documents.
 *
 * `<Suspense>` is required: the sidebar and the scroll reset read
 * `usePathname()`, which is only available at runtime and would otherwise block
 * prerendering.
 */
export default function DashboardLayout({ children }: LayoutProps<"/">) {
  return (
    <Suspense>
      <AppShell>
        <RouteScrollReset />
        {children}
      </AppShell>
    </Suspense>
  );
}
