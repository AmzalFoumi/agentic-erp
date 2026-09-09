/**
 * The chat panel's two layouts, and where the choice is stored.
 *
 * Framework-free on purpose: this module is the whole of the docked/expanded
 * decision — the mode values, how the stored choice is read, and how it is
 * written — with no React in it. `chat-shell.tsx` reads the mode through
 * `useSyncExternalStore` (snapshot = `readStoredMode`) and owns the React-side
 * subscriber list; it and `agent-panel.tsx` (which imports the `ChatMode` type)
 * are the callers.
 *
 * "docked"   — the 256px right rail (today's only layout).
 * "expanded" — the panel fills the page content area; the page is hidden
 *              (display:none), still mounted. Top nav + side nav stay visible.
 *
 * Persistence: `localStorage` under `CHAT_MODE_STORAGE_KEY`, no TTL, a bad
 * value falls back to the default. When `localStorage` is blocked (private
 * mode, some embedded webviews), the choice is held in `memoryMode` for the
 * session instead — the toggle still works, it just does not survive a reload.
 */
export type ChatMode = "docked" | "expanded";

export const CHAT_MODE_STORAGE_KEY = "agent-panel-mode";

// Session fallback for when localStorage is unavailable. Once set (either by a
// write, or because a read threw), it is the source of truth for this tab so
// the store's snapshot actually changes and React re-renders.
let memoryMode: ChatMode | null = null;

export function readStoredMode(): ChatMode {
  if (memoryMode !== null) return memoryMode;
  if (typeof window === "undefined") return "docked";
  try {
    return window.localStorage.getItem(CHAT_MODE_STORAGE_KEY) === "expanded"
      ? "expanded"
      : "docked";
  } catch {
    // Storage blocked — fall back to memory (still null here, so "docked").
    memoryMode = "docked";
    return "docked";
  }
}

export function writeStoredMode(mode: ChatMode): void {
  // Set the in-memory value first so it is correct whether or not the
  // localStorage write below succeeds.
  memoryMode = mode;
  try {
    window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, mode);
  } catch {
    // Storage blocked — the memory value above carries the choice for this
    // session.
  }
}

export function nextMode(current: ChatMode): ChatMode {
  return current === "docked" ? "expanded" : "docked";
}
