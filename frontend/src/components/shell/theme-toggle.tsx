"use client";

import { useEffect, useState } from "react";

/**
 * Toggles the `.dark` class on <html>. globals.css already defines both
 * palettes (:root and .dark); this component only decides which is active.
 * Light is the default because nothing in the generated design asked for
 * dark-by-default, unlike density where "dense" was a deliberate call.
 */
export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem("theme");
    const isDark = stored === "dark";
    setDark(isDark);
    document.documentElement.classList.toggle("dark", isDark);
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    window.localStorage.setItem("theme", next ? "dark" : "light");
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="rounded-(--radius) border border-border bg-secondary px-3 py-1 text-xs text-foreground"
    >
      {dark ? "Dark" : "Light"}
    </button>
  );
}
