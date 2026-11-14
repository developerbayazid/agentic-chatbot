"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * Ephemeral interface state only. Backend data (threads, documents, approvals)
 * belongs to TanStack Query — duplicating it here would create two caches that
 * can disagree.
 */
interface UiState {
  /** Desktop sidebar collapsed to icons. */
  sidebarCollapsed: boolean;
  /** Mobile drawer open. Not persisted: it is a momentary interaction. */
  mobileNavOpen: boolean;

  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setMobileNavOpen: (open: boolean) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      mobileNavOpen: false,

      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setMobileNavOpen: (mobileNavOpen) => set({ mobileNavOpen }),
    }),
    {
      name: "bayazid-ui",
      // Persist the layout preference only; never an open drawer.
      partialize: (state) => ({ sidebarCollapsed: state.sidebarCollapsed }),
    },
  ),
);
