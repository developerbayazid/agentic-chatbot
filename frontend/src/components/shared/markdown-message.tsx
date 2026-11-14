"use client";

import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useTheme } from "next-themes";

import { cn } from "@/lib/utils/cn";

/**
 * Assistant markdown.
 *
 * Safe by construction: react-markdown renders to React elements and never emits
 * raw HTML, so no sanitizer is needed and `dangerouslySetInnerHTML` is unused.
 * Links are restricted to http(s)/mailto/same-origin so a `javascript:` URL
 * cannot be produced.
 */
export function MarkdownMessage({
  content,
  className,
}: {
  content: string;
  className?: string;
}) {
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";

  return (
    <div className={cn("text-[15px] leading-[1.7] text-foreground", className)}>
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const safe = sanitizeHref(href);

            if (!safe) return <span>{children}</span>;

            return (
              <a
                href={safe}
                target="_blank"
                rel="noopener noreferrer nofollow"
                className="text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
              >
                {children}
              </a>
            );
          },
          pre: ({ children }) => <>{children}</>,
          code: ({ className: codeClass, children }) => {
            const text = String(children ?? "").replace(/\n$/, "");
            const language = /language-(\w+)/.exec(codeClass ?? "")?.[1];

            if (!language && !text.includes("\n")) {
              return (
                <code className="rounded bg-surface-hover px-[0.35em] py-[0.15em] font-mono text-[0.87em]">
                  {text}
                </code>
              );
            }

            return <CodeBlock code={text} language={language} dark={dark} />;
          },
          table: ({ children }) => (
            <div className="my-4 overflow-x-auto">
              <table className="w-full border-collapse text-[13.5px]">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-border px-2.5 py-1.5 text-left font-medium text-foreground">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-border px-2.5 py-1.5">{children}</td>
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-3 border-l-2 border-border-strong pl-4 italic text-muted-strong">
              {children}
            </blockquote>
          ),
          ul: ({ children }) => (
            <ul className="my-2.5 list-disc space-y-1 pl-5 marker:text-muted">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="my-2.5 list-decimal space-y-1 pl-5 marker:text-muted">
              {children}
            </ol>
          ),
          h1: ({ children }) => (
            <h1 className="mb-2 mt-5 text-[1.15em] font-semibold">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2 mt-4 text-[1.05em] font-semibold">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-1.5 mt-3 text-[0.98em] font-semibold">{children}</h3>
          ),
          p: ({ children }) => <p className="my-2.5">{children}</p>,
          hr: () => <hr className="my-5 border-border" />,
          strong: ({ children }) => (
            <strong className="font-semibold">{children}</strong>
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}

function CodeBlock({
  code,
  language,
  dark,
}: {
  code: string;
  language?: string;
  dark: boolean;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked; the code is still selectable.
    }
  }

  return (
    <div className="my-3 overflow-hidden rounded-lg border border-border bg-code-surface">
      <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
        <span className="font-mono text-[11px] text-muted">
          {language ?? "text"}
        </span>
        <button
          type="button"
          onClick={() => void copy()}
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted transition-colors hover:bg-surface-hover hover:text-foreground"
          aria-label={copied ? "Copied" : "Copy code"}
        >
          {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <div className="overflow-x-auto">
        <SyntaxHighlighter
          language={language ?? "text"}
          style={dark ? oneDark : oneLight}
          customStyle={{
            margin: 0,
            padding: "0.85rem 1rem",
            background: "transparent",
            fontSize: "0.8125rem",
            lineHeight: 1.65,
          }}
          codeTagProps={{ style: { fontFamily: "var(--font-mono)" } }}
          wrapLongLines={false}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}

/** Only absolute http(s), mailto, same-origin paths, and fragments survive. */
export function sanitizeHref(href: string | undefined): string | null {
  if (!href) return null;

  const trimmed = href.trim();

  if (/^(https?:|mailto:)/i.test(trimmed)) return trimmed;
  if (trimmed.startsWith("/") || trimmed.startsWith("#")) return trimmed;

  return null;
}
