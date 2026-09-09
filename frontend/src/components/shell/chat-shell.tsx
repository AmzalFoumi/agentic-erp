"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { AgentPanel } from "./agent-panel";
import {
  CHAT_MODE_STORAGE_KEY,
  nextMode,
  readStoredMode,
  type ChatMode,
} from "./chat-mode";
import { Nav } from "./nav";
import { cn } from "@/lib/utils";

/**
 * The signed-in content row: side nav, the page, and the agent panel.
 *
 * Owns `mode`. "docked" is the 256px rail; "expanded" hides the page
 * (display:none, still mounted — no unmount, no route change, nothing for
 * ThunderID to re-evaluate) and lets the panel fill the content area.
 *
 * Hydration: the server has no localStorage, so it always renders "docked".
 * `mode` uses a lazy `useState` initializer (the same pattern as
 * density-toggle.tsx) so a returning user's stored "expanded" is applied on
 * the client's first render — no set-state-in-effect. The two elements whose
 * className depends on `mode` (`<main>` here, the panel `<aside>`) carry
 * `suppressHydrationWarning` so that client-vs-server className difference is
 * not reported as a mismatch; everything inside them hydrates normally.
 */
function persistMode(mode: ChatMode) {
  try {
    window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, mode);
  } catch {
    // Storage unavailable (private mode / disabled) — the choice just won't
    // survive a reload this session.
  }
}

export function ChatShell({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ChatMode>(readStoredMode);

  const setModePersisted = useCallback((next: ChatMode) => {
    setMode(next);
    persistMode(next);
  }, []);

  const toggleMode = useCallback(() => {
    setMode((current) => {
      const next = nextMode(current);
      persistMode(next);
      return next;
    });
  }, []);

  // Esc collapses, but only while expanded, so it never competes with a
  // dialog/menu Esc handler in the docked layout.
  useEffect(() => {
    if (mode !== "expanded") return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setModePersisted("docked");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mode, setModePersisted]);

  const expanded = mode === "expanded";

  return (
    <div className="flex flex-1 min-h-0">
      <Nav />
      <main
        className={cn(
          "flex-1 min-w-0 overflow-auto p-section",
          expanded && "hidden",
        )}
        suppressHydrationWarning
      >
        {children}
      </main>
      <AgentPanel mode={mode} onToggleMode={toggleMode} />
    </div>
  );
}
