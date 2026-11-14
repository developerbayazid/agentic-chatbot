"use client";

/** Minimal greeting shown when a conversation has no messages yet. */
export function WelcomeScreen({ onPick }: { onPick: (prompt: string) => void }) {
  const examples = [
    "What does the handbook say about onboarding?",
    "Which products are running low?",
    "Summarise the policies document",
  ];

  return (
    <div className="flex min-h-full flex-col items-center justify-center px-6 py-16 text-center">
      <span
        aria-hidden
        className="grid size-10 place-items-center rounded-xl bg-accent text-[15px] font-semibold text-accent-contrast"
      >
        B
      </span>

      <h1 className="mt-5 text-[22px] font-medium tracking-tight">
        How can I help today?
      </h1>
      <p className="mt-2 max-w-md text-[14.5px] leading-relaxed text-muted">
        Ask about your documents, check inventory, or request an action that
        needs your approval.
      </p>

      <div className="mt-7 flex w-full max-w-lg flex-col gap-2">
        {examples.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onPick(prompt)}
            className="w-full rounded-xl border border-border px-4 py-2.5 text-left text-[13.5px] text-muted-strong transition-colors hover:border-border-strong hover:bg-surface hover:text-foreground"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
