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
 * value falls back to the default. `localStorage` is the only source of truth
 * on the happy path, so a cross-tab `storage` event stays authoritative. Only
 * when `localStorage` is blocked (private mode, some embedded webviews) is the
 * choice held in `memoryMode` for the session instead — the toggle still
 * works, it just does not survive a reload.
 */
export type ChatMode = "docked" | "expanded";

export const CHAT_MODE_STORAGE_KEY = "agent-panel-mode";

// Session fallback, used ONLY when localStorage is unavailable (private mode,
// some embedded webviews). The happy path never touches this — it always goes
// through localStorage — so a cross-tab `storage` event stays authoritative.
let memoryMode: ChatMode | null = null;

export function readStoredMode(): ChatMode {
  if (typeof window === "undefined") return "docked";
  try {
    return window.localStorage.getItem(CHAT_MODE_STORAGE_KEY) === "expanded"
      ? "expanded"
      : "docked";
  } catch {
    // Storage blocked — use the session fallback.
    return memoryMode ?? "docked";
  }
}

export function writeStoredMode(mode: ChatMode): void {
  try {
    window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, mode);
  } catch {
    // Storage blocked — hold the choice in memory for this session.
    memoryMode = mode;
  }
}

export function nextMode(current: ChatMode): ChatMode {
  return current === "docked" ? "expanded" : "docked";
}
