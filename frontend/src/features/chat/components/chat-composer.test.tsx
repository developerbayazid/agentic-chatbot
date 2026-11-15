import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { ChatComposer } from "@/features/chat/components/chat-composer";
import { buildCommands } from "@/features/commands/registry";

function noopActions() {
  const fn = () => {};
  return {
    newChat: fn,
    openThreads: fn,
    showHistory: fn,
    renameThread: fn,
    deleteThread: fn,
    openApprovals: fn,
    openDocuments: fn,
    showHelp: fn,
  };
}

const commands = buildCommands(noopActions());

/** Hosts the composer's controlled state the way the real view does. */
function Host({
  onSend = vi.fn(),
  onCommand = vi.fn(),
  filterCommands = (q: string) => commands.filter((c) => c.name.startsWith(q)),
}: {
  onSend?: (message: string) => void;
  onCommand?: (command: (typeof commands)[number]) => void;
  filterCommands?: (query: string) => typeof commands;
}) {
  const [value, setValue] = useState("");
  return (
    <ChatComposer
      value={value}
      onChange={setValue}
      onSend={onSend}
      onStop={() => {}}
      onCommand={onCommand}
      filterCommands={filterCommands}
      streaming={false}
    />
  );
}

const box = () => screen.getByLabelText("Message");

describe("composer", () => {
  it("does not open the menu for ordinary prose", async () => {
    const user = userEvent.setup();
    render(<Host />);

    await user.type(box(), "what is 2/3 as a decimal");

    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("opens the menu on a leading slash", async () => {
    const user = userEvent.setup();
    render(<Host />);

    await user.type(box(), "/");

    expect(screen.getByRole("listbox")).toBeTruthy();
  });

  it("filters as characters are typed", async () => {
    const user = userEvent.setup();
    render(<Host />);

    await user.type(box(), "/m");

    const options = screen.getAllByRole("option");
    expect(options.length).toBeGreaterThan(0);
    for (const option of options) {
      expect(option.textContent).toMatch(/^\/m/);
    }
  });

  it("selects the highlighted command with Enter and clears the input", async () => {
    const user = userEvent.setup();
    const onCommand = vi.fn();
    render(<Host onCommand={onCommand} />);

    await user.type(box(), "/new");
    await user.keyboard("{Enter}");

    expect(onCommand).toHaveBeenCalledTimes(1);
    expect(onCommand.mock.calls[0][0].name).toBe("/new");
    // Enter selected a command rather than sending a message.
    expect(box()).toHaveValue("");
  });

  it("moves the highlight with the arrow keys", async () => {
    const user = userEvent.setup();
    const onCommand = vi.fn();
    render(<Host onCommand={onCommand} />);

    await user.type(box(), "/");
    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");

    // Third entry in registry order.
    expect(onCommand.mock.calls[0][0].name).toBe("/history");
  });

  it("closes the menu on Escape", async () => {
    const user = userEvent.setup();
    render(<Host />);

    await user.type(box(), "/");
    expect(screen.getByRole("listbox")).toBeTruthy();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("sends plain text on Enter and keeps Shift+Enter for new lines", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<Host onSend={onSend} />);

    await user.type(box(), "hello{Shift>}{Enter}{/Shift}world");
    expect(onSend).not.toHaveBeenCalled();
    expect(box()).toHaveValue("hello\nworld");

    await user.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledWith("hello\nworld");
  });

  it("marks planned commands as Soon in the menu", async () => {
    const user = userEvent.setup();
    render(<Host />);

    await user.type(box(), "/skills");

    const option = screen.getAllByRole("option")[0];
    expect(option.textContent).toContain("Soon");
  });
});
