"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Light only for this phase.
 *
 * The palette in `globals.css` defines a single, designed black-and-white
 * experience. Offering a dark switch now would ship a half-specified theme, so
 * the provider pins light and stays only as the seam for adding a deliberate
 * dark palette later.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="light"
      forcedTheme="light"
      enableSystem={false}
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
