"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, LogIn } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api/errors";

/**
 * Sign in with an operator API key. The key is exchanged for a JWT by the BFF
 * (`/api/auth/login`), which stores it in an HttpOnly cookie; the token never
 * reaches this component.
 */
export default function LoginPage() {
  const router = useRouter();
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();

    if (!apiKey.trim() || pending) {
      return;
    }

    setPending(true);
    setError(null);

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ api_key: apiKey.trim() }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          body?.error?.message ?? "Sign in failed. Check your API key.",
        );
      }

      router.replace("/chat");
      router.refresh();
    } catch (cause) {
      setError(errorMessage(cause));
      setPending(false);
      return;
    }

    setPending(false);
  }

  return (
    <div className="w-full max-w-sm">
      <div className="mb-8 text-center">
        <span
          aria-hidden
          className="mx-auto grid size-10 place-items-center rounded-xl bg-accent text-[15px] font-semibold text-accent-contrast"
        >
          B
        </span>
        <h1 className="mt-4 text-[19px] font-medium tracking-tight">BAYAZID AI</h1>
        <p className="mt-1.5 text-[13.5px] text-muted">
          Sign in with your operator API key
        </p>
      </div>

      <form onSubmit={submit} className="space-y-3">
        <label className="block text-[12.5px] font-medium text-muted" htmlFor="api-key">
          API key
        </label>
        <Input
          id="api-key"
          type="password"
          autoComplete="off"
          autoFocus
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="Your operator key"
          aria-describedby={error ? "login-error" : undefined}
          aria-invalid={Boolean(error)}
        />

        {error && (
          <p id="login-error" role="alert" className="text-[13px] text-danger">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={pending}>
          {pending ? <Loader2 className="animate-spin" /> : <LogIn />}
          {pending ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <p className="mt-6 text-center text-[11.5px] leading-relaxed text-muted">
        Keys are configured by the operator in the backend&rsquo;s{" "}
        <code className="font-mono text-[11px]">API_KEYS</code>. Your session is
        kept in a secure cookie and expires with the token.
      </p>
    </div>
  );
}
