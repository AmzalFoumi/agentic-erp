"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Thin re-export so the rest of the app imports from `@/components/shell`
 * rather than reaching into `next-themes` directly — same reasoning as the
 * typed API client having exactly one seam.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider attribute="class" defaultTheme="light" enableSystem={false}>
      {children}
    </NextThemesProvider>
  );
}
