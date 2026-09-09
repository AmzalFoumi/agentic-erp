"use client";

import { useCallback, useEffect, useSyncExternalStore, type ReactNode } from "react";

import { AgentPanel } from "./agent-panel";
import {
  CHAT_MODE_STORAGE_KEY,
  nextMode,
  readStoredMode,
  writeStoredMode,
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
 * Hydration: `mode` comes from `useSyncExternalStore` — the server snapshot is
 * always the constant "docked" (no localStorage there), the client snapshot is
 * `readStoredMode()` (a primitive string). React renders the server snapshot
 * during hydration and only swaps to the stored value on the following commit,
 * so a returning "expanded" user gets no hydration mismatch anywhere in the
 * tree (not the `<aside>` className, not the `ExpandToggle` icon/aria inside
 * it). Subscribing to the `storage` event also keeps two open tabs in step.
 *
 * The persist logic (and its in-memory fallback for blocked storage) lives in
 * `chat-mode.ts`; this module only bridges it to React via `notify`.
 */
const listeners = new Set<() => void>();

function subscribe(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  const onStorage = (event: StorageEvent) => {
    if (event.key === CHAT_MODE_STORAGE_KEY) onStoreChange();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onStoreChange);
    window.removeEventListener("storage", onStorage);
  };
}

function getServerSnapshot(): ChatMode {
  return "docked";
}

function setMode(mode: ChatMode) {
  writeStoredMode(mode);
  // The `storage` event does not fire in the tab that made the change, so
  // notify local subscribers explicitly.
  listeners.forEach((listener) => listener());
}

export function ChatShell({ children }: { children: ReactNode }) {
  const mode = useSyncExternalStore(subscribe, readStoredMode, getServerSnapshot);

  const toggleMode = useCallback(() => {
    setMode(nextMode(readStoredMode()));
  }, []);

  // Esc collapses, but only while expanded, so it never competes with a
  // dialog/menu Esc handler in the docked layout.
  useEffect(() => {
    if (mode !== "expanded") return;
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented) return;
      if (event.key === "Escape") setMode("docked");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mode]);

  const expanded = mode === "expanded";

  return (
    <div className="flex flex-1 min-h-0">
      <Nav />
      <main
        className={cn(
          "flex-1 min-w-0 overflow-auto p-section",
          expanded && "hidden",
        )}
      >
        {children}
      </main>
      <AgentPanel mode={mode} onToggleMode={toggleMode} />
    </div>
  );
}
