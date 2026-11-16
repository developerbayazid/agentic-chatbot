import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Layout invariants found by browser testing, not by reading code.
 *
 * Two bugs shipped because nothing asserted them:
 *  - `main` was `overflow-hidden`, so any page taller than the viewport (the
 *    tool catalog) was silently clipped and looked empty;
 *  - a global `* { scrollbar-width: thin }` drew a scrollbar inside the
 *    composer's textarea, beside the send button.
 *
 * These read the source rather than rendering, because the failure mode is a
 * class name quietly reverting and the assertions are about static structure.
 */
const ROOT = join(process.cwd(), "src");

function read(path: string): string {
  return readFileSync(join(ROOT, path), "utf8");
}

describe("app shell scrolling", () => {
  it("lets the main region scroll so long pages are not clipped", () => {
    const shell = read("components/layout/app-shell.tsx");

    expect(shell).toContain("overflow-y-auto");
    // The regression: a non-scrolling main clipped the tool catalog.
    expect(shell).not.toMatch(/<main[^>]*overflow-hidden/);
  });

  it("opts real scroll containers into the styled scrollbar", () => {
    const shell = read("components/layout/app-shell.tsx");
    const conversation = read("features/chat/components/conversation-view.tsx");
    const threads = read("features/threads/components/thread-list.tsx");

    for (const source of [shell, conversation, threads]) {
      expect(source).toContain("scroll-area");
    }
  });
});

describe("composer", () => {
  it("never shows a scrollbar beside the send button", () => {
    const css = read("app/globals.css");

    // Textareas hide their scrollbar; they grow with content instead.
    expect(css).toMatch(/textarea\s*\{[^}]*scrollbar-width:\s*none/);
    expect(css).toContain("textarea::-webkit-scrollbar");
  });

  it("does not apply a scrollbar style to every element", () => {
    const css = read("app/globals.css");

    // The regression: `* { scrollbar-width: thin }` leaked into the textarea.
    // Checked without the `s` flag, which this tsconfig target does not support.
    const globalRule = css
      .split("\n")
      .findIndex((line) => line.trim() === "* {" && !line.startsWith(" "));

    if (globalRule !== -1) {
      const block = css.slice(globalRule, css.indexOf("}", globalRule));
      expect(block).not.toContain("scrollbar-width");
    }
  });

  it("is fully rounded", () => {
    const composer = read("features/chat/components/chat-composer.tsx");

    expect(composer).toContain("rounded-[1.75rem]");
    expect(composer).toContain("rounded-full");
  });
});

describe("tools page", () => {
  it("renders every tool the API returns, grouped by category", () => {
    const page = read("app/(dashboard)/tools/page.tsx");

    // No slice/limit: the page must list all of them, not a preview.
    expect(page).not.toMatch(/\.slice\(0,\s*\d+\)/);
    expect(page).toContain("catalog.data?.count");
    expect(page).toContain("groups.map");
  });
});

describe("single-page routing", () => {
  it("serves /chat and /chat/<id> from one client route", () => {
    // A single optional catch-all so switching conversations (and creating one)
    // updates the URL without remounting the view, which would drop the streamed
    // reply and force a refetch.
    const page = read("app/(dashboard)/chat/[[...threadId]]/page.tsx");

    expect(page).toContain('"use client"');
    expect(page).toContain("useParams");
  });

  it("never awaits `params` in a server component", () => {
    // This was the reported defect: an `async` page awaiting `params` forced a
    // server round-trip per navigation, and Next logged
    // "encountered URL data during prerendering or a navigation".
    const page = read("app/(dashboard)/chat/[[...threadId]]/page.tsx");

    expect(page).not.toContain("await params");
    expect(page).not.toMatch(/export default async function/);
  });

  it("does not keep the old per-segment chat routes", () => {
    // Both would shadow or conflict with the consolidated route.
    expect(existsSync(join(ROOT, "app/(dashboard)/chat/page.tsx"))).toBe(false);
    expect(existsSync(join(ROOT, "app/(dashboard)/chat/[threadId]"))).toBe(false);
  });
});
