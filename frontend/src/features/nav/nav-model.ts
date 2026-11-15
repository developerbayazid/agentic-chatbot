import type { LucideIcon } from "lucide-react";
import { Blocks, FileText, Puzzle, ShieldCheck, Wrench } from "lucide-react";

/**
 * Navigation availability.
 *
 * "soon" sections are real navigation targets, but they state plainly that the
 * capability is not implemented. Nothing in the UI may imply otherwise.
 */
export type Availability = "available" | "soon";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  availability: Availability;
  /** Shown as a chip for "soon" items. */
  blurb?: string;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

/** Workspace features that genuinely exist. */
export const WORKSPACE_NAV: NavItem[] = [
  { href: "/documents", label: "Documents", icon: FileText, availability: "available" },
  { href: "/approvals", label: "Approvals", icon: ShieldCheck, availability: "available" },
  { href: "/tools", label: "Tools", icon: Wrench, availability: "available" },
];

/**
 * Planned capabilities. The routes exist so the navigation is honest and the
 * shape is settled, but each page says it is not available yet.
 */
export const PLATFORM_NAV: NavItem[] = [
  {
    href: "/skills",
    label: "Skills",
    icon: Blocks,
    availability: "soon",
    blurb: "Reusable agent skills will be supported in a future update.",
  },
  {
    href: "/plugins",
    label: "Plugins",
    icon: Puzzle,
    availability: "soon",
    blurb: "Installable plugins will be supported in a future update.",
  },
  {
    href: "/mcp",
    label: "MCP",
    icon: Blocks,
    availability: "soon",
    blurb: "External MCP servers will be supported in a future update.",
  },
];
