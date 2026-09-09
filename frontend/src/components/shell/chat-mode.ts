/**
 * The chat panel's two layouts, and where the choice is stored.
 *
 * Framework-free on purpose: this is the whole of the docked/expanded decision,
 * with no React in it, so it can be reasoned about (and later unit-tested) on
 * its own. `chat-shell.tsx` is the only caller.
 *
 * "docked"   — the 256px right rail (today's only layout).
 * "expanded" — the panel fills the page content area; the page is hidden
 *              (display:none), still mounted. Top nav + side nav stay visible.
 *
 * Same persistence pattern as the density toggle (see density-toggle.tsx):
 * localStorage, read once on mount, no TTL, a bad value falls back to the
 * default rather than throwing.
 */
export type ChatMode = "docked" | "expanded";

export const CHAT_MODE_STORAGE_KEY = "agent-panel-mode";

export function readStoredMode(): ChatMode {
  if (typeof window === "undefined") return "docked";
  try {
    return window.localStorage.getItem(CHAT_MODE_STORAGE_KEY) === "expanded"
      ? "expanded"
      : "docked";
  } catch {
    // Private-mode / disabled storage — behave as a first-time visitor.
    return "docked";
  }
}

export function nextMode(current: ChatMode): ChatMode {
  return current === "docked" ? "expanded" : "docked";
}
