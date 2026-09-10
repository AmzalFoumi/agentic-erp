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
 * value falls back to the default. Successful reads keep the in-memory value
 * synchronized, so a cross-tab `storage` event stays authoritative. If any
 * storage access fails (private mode, some embedded webviews), the in-memory
 * value becomes authoritative for the rest of the session — the toggle still
 * works, it just does not survive a reload.
 */
export type ChatMode = "docked" | "expanded";

export const CHAT_MODE_STORAGE_KEY = "agent-panel-mode";

// Keep a synchronized snapshot so a later storage failure can fall back to the
// last known mode. Once storage fails, avoid it for the rest of the session.
let memoryMode: ChatMode = "docked";
let storageUnavailable = false;

export function readStoredMode(): ChatMode {
  if (typeof window === "undefined") return "docked";
  if (storageUnavailable) return memoryMode;

  try {
    memoryMode = window.localStorage.getItem(CHAT_MODE_STORAGE_KEY) === "expanded"
      ? "expanded"
      : "docked";
    return memoryMode;
  } catch {
    storageUnavailable = true;
    return memoryMode;
  }
}

export function writeStoredMode(mode: ChatMode): void {
  memoryMode = mode;
  if (storageUnavailable) return;

  try {
    window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, mode);
  } catch {
    storageUnavailable = true;
  }
}

export function nextMode(current: ChatMode): ChatMode {
  return current === "docked" ? "expanded" : "docked";
}
