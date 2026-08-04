"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";

/**
 * Toggles the `.dark` class on <html> via next-themes, which handles the
 * flash-of-wrong-theme and hydration-mismatch problems that a hand-rolled
 * localStorage + useEffect toggle can't: it sets the class from an inline
 * script before hydration, so server and client never disagree. globals.css
 * already defines both palettes (:root and .dark); this component only
 * decides which is active. Light is the default (see ThemeProvider) because
 * nothing in the generated design asked for dark-by-default, unlike density
 * where "dense" was a deliberate call.
 */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // The server has no notion of the stored theme, so the label must render
  // something theme-independent until after hydration — otherwise this is
  // exactly the mismatch next-themes exists to avoid. This is next-themes'
  // own documented "mounted" guard, not a case the lint rule intends to
  // flag: there is no external system to synchronize with here, only a
  // one-time signal that hydration has completed.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setMounted(true), []);

  const dark = mounted && resolvedTheme === "dark";

  return (
    <button
      type="button"
      onClick={() => setTheme(dark ? "light" : "dark")}
      className="rounded-(--radius) border border-border bg-secondary px-3 py-1 text-xs text-foreground"
      suppressHydrationWarning
    >
      {mounted ? (dark ? "Dark" : "Light") : "Light"}
    </button>
  );
}
