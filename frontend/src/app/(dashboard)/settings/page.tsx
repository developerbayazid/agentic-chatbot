"use client";

import { useEffect, useState } from "react";
import { Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useSession } from "@/features/auth/hooks/use-session";

/** Read-only application information; the theme is fixed for now. */
export default function SettingsPage() {
  const { subject, logout } = useSession();
  const [health, setHealth] = useState<string>("checking…");

  useEffect(() => {
    let cancelled = false;

    void fetch("/api/backend/health")
      .then(async (response) => {
        if (cancelled) return;
        if (!response.ok) {
          setHealth(`unavailable (${response.status})`);
          return;
        }
        const body = (await response.json()) as { status?: string };
        setHealth(body.status ?? "ok");
      })
      .catch(() => {
        if (!cancelled) setHealth("unreachable");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto w-full max-w-2xl px-5 py-8">
      <header>
        <h1 className="text-[19px] font-medium tracking-tight">Settings</h1>
        <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">
          Frontend preferences. Server behaviour is configured through the
          backend&rsquo;s environment.
        </p>
      </header>

      <section className="mt-7">
        <h2 className="text-[13px] font-medium text-foreground">Appearance</h2>
        <p className="mt-1 text-[12.5px] leading-relaxed text-muted">
          BAYAZID AI currently has a single, designed black-and-white theme. A
          dark theme is planned but not implemented, so there is no switch to
          offer yet.
        </p>
        <div className="mt-2.5 flex items-center gap-2 text-[12.5px] text-muted-strong">
          <Sun className="size-3.5" />
          Light
          <span className="rounded px-1 py-px text-[10px] font-medium uppercase tracking-wide text-muted ring-1 ring-inset ring-border-strong">
            Active
          </span>
        </div>
      </section>

      <section className="mt-7 border-t border-border pt-6">
        <h2 className="text-[13px] font-medium text-foreground">Session</h2>
        <dl className="mt-2 space-y-1.5 text-[13px]">
          <div className="flex gap-2">
            <dt className="w-32 text-muted">Signed in as</dt>
            <dd className="font-mono text-foreground">{subject ?? "—"}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-32 text-muted">Session storage</dt>
            <dd className="text-muted-strong">
              HttpOnly cookie (not readable by JavaScript)
            </dd>
          </div>
        </dl>

        <Button variant="secondary" size="sm" className="mt-3" onClick={() => void logout()}>
          Sign out
        </Button>
      </section>

      <section className="mt-7 border-t border-border pt-6">
        <h2 className="text-[13px] font-medium text-foreground">Application</h2>
        <dl className="mt-2 space-y-1.5 text-[13px]">
          <div className="flex gap-2">
            <dt className="w-32 text-muted">Backend health</dt>
            <dd className="font-mono text-foreground">{health}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-32 text-muted">Version</dt>
            <dd className="font-mono text-foreground">0.2.0</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
