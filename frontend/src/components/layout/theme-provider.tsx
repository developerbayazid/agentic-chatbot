"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Light is the primary experience. Dark exists as an optional preference and is
 * never the initial state.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="light"
      enableSystem={false}
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
