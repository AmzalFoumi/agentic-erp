# Gate 31 — Chat Fullscreen / Expand Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The agent panel can switch between the 256 px right rail it is today and filling the
entire page content area, with the top navbar and side nav still visible, and the choice is
remembered across reloads.

**Architecture:** One new client component, `frontend/src/components/shell/chat-shell.tsx`, wraps
the `<Nav>` + `<main>` + `<AgentPanel>` row that currently lives inline in `layout.tsx`. It owns a
`mode: "docked" | "expanded"` state (persisted to `localStorage`, same pattern as the density
toggle). `layout.tsx` stays a Server Component and passes the server-rendered page in as
`children`. When `mode` is `expanded`, the page wrapper gets the `hidden` class (`display:none`,
still mounted — no unmount, no route change, no refetch) and the panel's `<aside>` grows from
`w-64` to `flex-1`. `AgentPanel` gains two props (`mode`, `onToggleMode`) and renders an
expand/collapse icon button in its header.

**Tech Stack:** Next.js 16 (App Router, `src/` layout, Turbopack), React 19, Tailwind v4,
`@base-ui/react` / shadcn base-nova primitives, `lucide-react` for icons. **No new dependencies.**

**Spec:** `docs/superpowers/specs/2026-09-09-chatbot-overhaul-design.md` — read "Priority 1 —
fullscreen / expand mode → Gate 31" and the "Hard constraints" section first. This plan implements
it task-by-task; where the two disagree, the spec is right.

## Global Constraints

Copied verbatim from the spec's "Hard constraints" — every task's requirements implicitly include
these:

- **No routing changes.** No new routes, no route renames, no changes to `src/proxy.ts` or
  `src/app/api/agent/[...path]/route.ts`.
- **No auth / permission / ThunderID changes.** No new scopes, no Console changes, no token
  handling changes. `deploy/aisle-box/` is not touched.
- **Frontend only.** No file outside `frontend/src/` changes except `docs/PLAN.md` and
  `docs/FRONTEND-PLAN.md` in the final task. No backend, no `agent/`.
- **The page is hidden, never unmounted.** Use the `hidden` class / attribute (`display:none`).
  Unmounting `children` would drop page client state and, worse, fire a fresh render/refetch when
  it remounts — the thing this design exists to avoid.
- **The ESLint architecture rules hold.** `chat-shell.tsx` is a component: it must not `import`
  from `openapi-fetch`, `@/lib/api/schema*`, or `server-only`, and must not call `fetch`. It only
  imports other components. Run `npm run lint` after every task.

Project working-agreement constraints that apply here:

- **The developer runs `npm run *` / `npx` / `git`.** This plan's verification steps tell you
  which commands to give the developer and what output to expect; you do not run them yourself.
- **Browser MCP (chrome-devtools) is allowed only after the developer has `npm run dev` running
  and says continue.** The dev stack (`scripts/dev-up-timed.sh`) and ThunderID are already up this
  session; test user is `amzal` / password `12345`.
- **Stop-gate discipline:** each task ends by explaining what changed, listing files touched, and
  handing off for a manual `git commit`. Do not push.
- **Commit message trailers:** end every commit message with
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01XruycPu9FKxDpuCES3GRC6`.

## The frontend has no test runner — how "test" works here

Confirmed during planning: `frontend/` has no vitest / jest / MSW and never did (the developer
chose to keep it that way for this gate). There are **no `*.test.tsx` files to write.** Every task
below is verified by, in order:

1. `npx tsc --noEmit` — clean (the frontend's "does it type-check").
2. `npm run lint` — clean (ESLint, including the restricted-import architecture rules).
3. `npm run build` — succeeds (`export const dynamic = "force-dynamic"` in `layout.tsx` already
   makes every route per-request, so the build does not try to prerender).
4. A scripted **chrome-devtools MCP walkthrough** (Task 3) — the behavioural check.

Pure logic (the `mode` reducer, the `localStorage` read) is written as small exported functions so
it *could* be unit-tested later, but this plan does not add a runner.

---

## File Structure

| File | New / Modified | Responsibility |
|---|---|---|
| `frontend/src/components/shell/chat-shell.tsx` | **New** | Client component. Owns `mode` state + `localStorage` persistence + `Esc`-to-collapse. Renders the `<Nav>` + page-wrapper + `<AgentPanel>` flex row. Switches the page wrapper to `hidden` and the panel to full width when expanded. |
| `frontend/src/components/shell/chat-mode.ts` | **New** | Pure, framework-free helpers: the `ChatMode` type, `STORAGE_KEY`, `readStoredMode()`, `nextMode()`. Kept separate so the storage/reducer logic is trivial to reason about and has no React in it. |
| `frontend/src/app/layout.tsx` | Modified (~lines 118–136) | Replace the inline `<div className="flex flex-1 min-h-0">…</div>` block inside `<SignedIn>` with `<ChatShell>{children}</ChatShell>`. Drop the now-unused `AgentPanel` / `Nav` imports (they move to `chat-shell.tsx`). Stays a Server Component. |
| `frontend/src/components/shell/agent-panel.tsx` | Modified | Accept `mode: ChatMode` and `onToggleMode: () => void` props on `AgentPanel`, thread them to both the "Connecting…" branch and `ConnectedAgentPanel`. Render an expand/collapse icon button in the header(s). Switch the `<aside>` width class `w-64` ↔ `flex-1` on `mode`. When expanded, constrain the scroll column + form to `max-w-3xl` centered. |

Nothing else in the tree renders `AgentPanel` or depends on the `<SignedIn>` layout shape —
verified during planning (`grep` for `AgentPanel` returns only `layout.tsx`).

---

## Task 1: `chat-mode.ts` helpers + `chat-shell.tsx` wrapper, wired into `layout.tsx` (docked-only, no visual change)

**Deliverable:** the layout row is refactored behind `ChatShell`, the app looks and behaves
exactly as before (always docked), type-checks, lints, builds.

**Files:**
- Create: `frontend/src/components/shell/chat-mode.ts`
- Create: `frontend/src/components/shell/chat-shell.tsx`
- Modify: `frontend/src/app/layout.tsx`

**Interfaces:**
- Produces:
  - `chat-mode.ts`: `export type ChatMode = "docked" | "expanded";`
    `export const CHAT_MODE_STORAGE_KEY = "agent-panel-mode";`
    `export function readStoredMode(): ChatMode` — SSR-safe, returns `"docked"` when
    `window` is undefined or the stored value is anything other than `"expanded"`.
    `export function nextMode(current: ChatMode): ChatMode` — flips the two.
  - `chat-shell.tsx`: `export function ChatShell({ children }: { children: React.ReactNode })`.
- Consumes: `Nav` from `./nav`, `AgentPanel` from `./agent-panel` (Task 2 gives `AgentPanel` its
  new props; in this task pass nothing and `AgentPanel` still has its old zero-prop signature).

- [ ] **Step 1: Write `frontend/src/components/shell/chat-mode.ts`**

```ts
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
```

- [ ] **Step 2: Write `frontend/src/components/shell/chat-shell.tsx` (docked-only for now)**

This task wires the component in without behaviour change. `mode` is fixed at `"docked"` here;
Task 2 makes it stateful. Keeping Task 1 a pure refactor means a reviewer can confirm "nothing
moved" before judging the new UX.

```tsx
"use client";

import type { ReactNode } from "react";

import { AgentPanel } from "./agent-panel";
import { Nav } from "./nav";

/**
 * The signed-in content row: side nav, the page, and the agent panel.
 *
 * Lifted out of layout.tsx (a Server Component) into its own client component
 * so it can own the docked/expanded state that gate 31 adds. `children` is the
 * server-rendered page, passed straight through — a client component rendering
 * server children is the standard App Router pattern and changes nothing about
 * how the page itself renders.
 *
 * Gate 31, task 1: structure only, always docked. Task 2 adds the mode state.
 */
export function ChatShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-1 min-h-0">
      <Nav />
      <main className="flex-1 min-w-0 overflow-auto p-section">{children}</main>
      <AgentPanel />
    </div>
  );
}
```

- [ ] **Step 3: Rewire `frontend/src/app/layout.tsx`**

In the `<SignedIn>` block, replace this (currently ~lines 129–135):

```tsx
              <div className="flex flex-1 min-h-0">
                <Nav />
                <main className="flex-1 min-w-0 overflow-auto p-section">
                  {children}
                </main>
                <AgentPanel />
              </div>
```

with:

```tsx
              <ChatShell>{children}</ChatShell>
```

Then fix the imports at the top of the file:
- Remove `import { AgentPanel } from "@/components/shell/agent-panel";`
- Remove `import { Nav } from "@/components/shell/nav";`
- Add `import { ChatShell } from "@/components/shell/chat-shell";`

Leave everything else in `layout.tsx` untouched — `<ThunderIDProvider>`, `<ThemeProvider>`,
`<SignedIn>` / `<SignedOut>`, the header `<div>` with `Logo` / `DensityToggle` / `ThemeToggle` /
`UserMenu`, and `export const dynamic = "force-dynamic"`. The `<SignedOut>` branch keeps its own
bare `<main>` and does **not** get a `ChatShell`.

- [ ] **Step 4: Give the developer the verification commands**

Ask the developer to run, from `frontend/`:

```bash
npx tsc --noEmit
npm run lint
npm run build
```

Expected: all three succeed with no errors. `tsc` in particular confirms the moved imports
resolve and `ChatShell`'s single prop is right. If `npm run build` complains about a prerender on
any route, stop — that means something other than this change regressed, because `force-dynamic`
is already set.

- [ ] **Step 5: Hand off for commit**

Explain: the signed-in layout row moved from inline JSX in `layout.tsx` into a new
`ChatShell` client component; no behaviour change; `chat-mode.ts` adds the (not yet used)
mode helpers. Files: `chat-mode.ts` (new), `chat-shell.tsx` (new), `layout.tsx` (imports +
one block). Suggested commit:

```
feat(chat): extract signed-in layout row into ChatShell wrapper

Gate 31, task 1. Move the <Nav> + <main> + <AgentPanel> row out of
layout.tsx into a new client component so it can own the docked/expanded
state gate 31 adds. Pure refactor: always docked, no visual change.
chat-mode.ts carries the (not yet wired) ChatMode type and localStorage
helpers.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XruycPu9FKxDpuCES3GRC6
```

---

## Task 2: mode state, persistence, toggle button, width switch, `Esc`, expanded readability

**Deliverable:** working expand/collapse. Clicking the header button fills the content area with
the panel and hides the page; clicking again restores it; `Esc` collapses; the choice survives a
reload.

**Files:**
- Modify: `frontend/src/components/shell/chat-shell.tsx`
- Modify: `frontend/src/components/shell/agent-panel.tsx`

**Interfaces:**
- Consumes: `ChatMode`, `CHAT_MODE_STORAGE_KEY`, `readStoredMode`, `nextMode` from `./chat-mode`.
- Produces: `AgentPanel` now has the signature
  `function AgentPanel({ mode, onToggleMode }: { mode: ChatMode; onToggleMode: () => void })`,
  and `ConnectedAgentPanel` takes the same two as extra props alongside its existing ones.

- [ ] **Step 1: Make `chat-shell.tsx` stateful**

Replace the Task 1 body with:

```tsx
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
 * `mounted` gate: the server renders this as "docked" (no localStorage there),
 * so a returning user who left it expanded would otherwise get a docked->
 * expanded hydration mismatch. Rendering "docked" until mounted, then applying
 * the stored value, is the same trick theme-toggle.tsx uses for its label.
 */
export function ChatShell({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ChatMode>("docked");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMode(readStoredMode());
    setMounted(true);
  }, []);

  const toggleMode = useCallback(() => {
    setMode((current) => {
      const next = nextMode(current);
      try {
        window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, next);
      } catch {
        // Storage unavailable — the toggle still works for this session.
      }
      return next;
    });
  }, []);

  // Esc collapses, but only while expanded, so it never competes with a
  // dialog/menu Esc handler in the docked layout.
  useEffect(() => {
    if (!mounted || mode !== "expanded") return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setMode("docked");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mounted, mode]);

  // Keep localStorage in step when Esc (which calls setMode directly) fires.
  useEffect(() => {
    if (!mounted) return;
    try {
      window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, mode);
    } catch {
      /* ignore */
    }
  }, [mounted, mode]);

  const expanded = mounted && mode === "expanded";

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
      <AgentPanel
        mode={expanded ? "expanded" : "docked"}
        onToggleMode={toggleMode}
      />
    </div>
  );
}
```

Note: the two `setItem` calls (in `toggleMode` and the sync effect) are deliberate — `toggleMode`
writes immediately so a reload right after a click is correct, and the effect covers the `Esc`
path which calls `setMode` directly. Writing the same value twice is harmless.

- [ ] **Step 2: Add the props and the toggle button to `agent-panel.tsx`**

At the top, add the import:

```tsx
import { Maximize2, Minimize2, X } from "lucide-react";
import type { ChatMode } from "./chat-mode";
```

(`X` is already imported — merge it into the one `lucide-react` line. Verify `Maximize2` /
`Minimize2` resolve against the installed `lucide-react` ^1.28 — they are long-standing icon
names; if the import errors, use `Expand` / `Shrink`.)

Change the `AgentPanel` signature and thread the props:

```tsx
export function AgentPanel({
  mode,
  onToggleMode,
}: {
  mode: ChatMode;
  onToggleMode: () => void;
}) {
```

In the **"Connecting…" branch** (`if (conversationId === null)`), replace the header line

```tsx
        <div className="text-sm font-semibold">Assistant</div>
```

with a header row that carries the expand toggle:

```tsx
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-semibold">Assistant</div>
          <ExpandToggle mode={mode} onToggleMode={onToggleMode} />
        </div>
```

and give that branch's `<aside>` the width switch (see Step 3 for the class).

Pass the props into `ConnectedAgentPanel`:

```tsx
    <ConnectedAgentPanel
      key={conversationId}
      conversationId={conversationId}
      initialMessages={initialMessages}
      mode={mode}
      onToggleMode={onToggleMode}
      onConversationChange={(newId) => {
        setInitialMessages([]);
        setConversationId(newId);
      }}
    />
```

Update `ConnectedAgentPanel`'s prop type to add:

```tsx
  mode,
  onToggleMode,
}: {
  conversationId: number;
  initialMessages: UIMessage[];
  mode: ChatMode;
  onToggleMode: () => void;
  onConversationChange: (id: number) => void;
}) {
```

In `ConnectedAgentPanel`'s header (the `<div className="flex items-center justify-between gap-2">`
holding the `X` "Clear chat" button), add the toggle **before** the `X` button:

```tsx
        <div className="flex items-center gap-1">
          <ExpandToggle mode={mode} onToggleMode={onToggleMode} />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setShowClearConfirm(true)}
            title="Clear chat"
            className="h-6 w-6 p-0"
          >
            <X className="size-4" />
          </Button>
        </div>
```

Add the small `ExpandToggle` component at the bottom of the file (below `ConnectedAgentPanel`):

```tsx
function ExpandToggle({
  mode,
  onToggleMode,
}: {
  mode: ChatMode;
  onToggleMode: () => void;
}) {
  const expanded = mode === "expanded";
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={onToggleMode}
      title={expanded ? "Collapse chat to the side" : "Expand chat to full screen"}
      aria-label={expanded ? "Collapse chat" : "Expand chat"}
      aria-pressed={expanded}
      className="h-6 w-6 p-0"
    >
      {expanded ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
    </Button>
  );
}
```

- [ ] **Step 3: Width switch on both `<aside>` elements**

Both `<aside>` elements today are:

```tsx
className="flex h-full w-64 min-h-0 shrink-0 flex-col gap-stack border-l border-border bg-card p-section"
```

Change both to switch on `mode` (import `cn` from `@/lib/utils` at the top of the file if not
already present):

```tsx
className={cn(
  "flex h-full min-h-0 flex-col gap-stack border-l border-border bg-card p-section",
  mode === "expanded" ? "flex-1" : "w-64 shrink-0",
)}
```

- [ ] **Step 4: Readability when expanded**

In `ConnectedAgentPanel`, the scroll container and the form should not stretch edge-to-edge in the
wide layout. Wrap their contents in a centered max-width column.

The scroll `<div ref={scrollRef} className="flex min-h-0 flex-1 flex-col gap-stack overflow-y-auto">`
becomes:

```tsx
      <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <div
          className={cn(
            "flex flex-col gap-stack",
            mode === "expanded" && "mx-auto w-full max-w-3xl",
          )}
        >
          {/* existing children: IdleState, MessageList, ThinkingIndicator,
              ToolCallCard, SuccessCard, error block — unchanged */}
        </div>
      </div>
```

And the `<form className="mt-auto flex shrink-0 gap-2 pt-stack" …>` gets the same treatment:

```tsx
      <form
        className={cn(
          "mt-auto flex shrink-0 gap-2 pt-stack",
          mode === "expanded" && "mx-auto w-full max-w-3xl",
        )}
        …
      >
```

Leave the `showClearConfirm` confirmation block where it is (it can stay full-width of the
`p-section` padding; it is small and transient).

- [ ] **Step 5: Give the developer the verification commands**

From `frontend/`:

```bash
npx tsc --noEmit
npm run lint
npm run build
```

Expected: all clean. `tsc` confirms the prop threading through `ChatShell` → `AgentPanel` →
`ConnectedAgentPanel` → `ExpandToggle` is consistent. `lint` will flag the `set-state-in-effect`
rule if the `Esc` effect is written carelessly — the version in Step 1 only calls `setMode` inside
an event handler, not synchronously in the effect body, so it is fine; if lint complains, that is
a real issue to fix, not to disable.

- [ ] **Step 6: Hand off for commit**

Explain: `ChatShell` now owns a `docked`/`expanded` mode, persisted to `localStorage`
(`agent-panel-mode`) exactly like the density toggle; `AgentPanel` gained an expand/collapse
button in its header, grows to `flex-1` when expanded, and centers its content at `max-w-3xl`;
`Esc` collapses; the page is hidden with `display:none`, never unmounted. Files:
`chat-shell.tsx`, `agent-panel.tsx`. Suggested commit:

```
feat(chat): add fullscreen expand mode to the agent panel

Gate 31, task 2. ChatShell owns a docked/expanded mode persisted to
localStorage (agent-panel-mode), same pattern as the density toggle.
Expanded hides the page with display:none (still mounted — no route
change, no refetch) and grows the panel <aside> from w-64 to flex-1,
with the message column centered at max-w-3xl. Header gets an
expand/collapse icon button; Esc collapses.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XruycPu9FKxDpuCES3GRC6
```

---

## Task 3: browser walkthrough verification + docs

**Deliverable:** the behaviour is confirmed in a real browser against the running dev stack, and
`docs/PLAN.md` / `docs/FRONTEND-PLAN.md` record the gate as done.

**Files:**
- Modify: `docs/PLAN.md` (gate 31 row)
- Modify: `docs/FRONTEND-PLAN.md` (a short note in the gate 13g list or a new dated line)

**Prerequisite:** confirm with the developer that `npm run dev` is up on `http://localhost:3000`
(the session's `dev-up-timed.sh` stack) and they say continue. Then use chrome-devtools MCP.

- [ ] **Step 1: Log in if needed**

Navigate to `http://localhost:3000`. If not signed in, sign in as `amzal` / `12345` via the
ThunderID flow (click "Advanced" → "Proceed to localhost (unsafe)" past the self-signed cert
warning if it appears — expected, documented in `CLAUDE.md`).

- [ ] **Step 2: Docked is the default**

On `/products`, take a snapshot. Expected: the assistant panel is the narrow right rail
(`w-64`), the products table fills the middle, the side nav and header are present. The header of
the panel shows an expand icon button next to the "Clear chat" X.

- [ ] **Step 3: Expand**

Click the expand button. Expected:
- The products table is **gone from view** (the `<main>` is `display:none`).
- The side nav (Products / New product / Expiring soon / Suppliers / Purchasing / Approvals) and
  the top header (Logo / Dense-Comfortable / theme / user menu) are **still visible**.
- The assistant panel now fills the whole content area; its message column is centered, not
  stretched edge to edge.
- The URL is **unchanged** (`/products`).
- In the network panel (`list_network_requests`), **no new document/RSC request** fired for the
  page as a result of the toggle.

- [ ] **Step 4: The conversation still works while expanded**

Type "What's low on stock right now?" and send. Expected: a normal streamed reply appears in the
expanded panel. (This confirms `useChat` state and the `/api/agent/...` transport are untouched by
the layout change.)

- [ ] **Step 5: Collapse restores the page**

Scroll the products page first? It is hidden — instead: before expanding in a fresh reload,
scroll the products table down a little, note a row near the bottom, then expand, then collapse.
Click the collapse button (now a "minimize" icon). Expected:
- The products table reappears at **the same scroll position** it was left at.
- The panel returns to the `w-64` rail.
- Still no route change, still no page refetch in the network panel.

(If scroll position is *not* preserved by `display:none` in this browser, note it in the PLAN.md
row as a known minor limitation — it is not a blocker, and client state / form inputs are
preserved regardless because the page stays mounted.)

- [ ] **Step 6: `Esc` collapses**

Expand again, press `Escape`. Expected: collapses to the rail.

- [ ] **Step 7: The choice survives a reload**

Expand, then reload the page (`navigate_page` to the same URL, or browser reload). Expected: the
panel comes back **expanded** (read from `localStorage`), after a brief moment in the docked
layout during hydration (the `mounted` gate — acceptable, matches how the theme toggle behaves).

- [ ] **Step 8: Signed-out is unaffected**

Open the user menu → sign out (or open an incognto-style fresh context if simpler). Navigate to
`/`. Expected: the marketing landing page renders normally, with **no assistant panel and no
expand control** — the `<SignedOut>` branch was never wrapped in `ChatShell`.

- [ ] **Step 9: Update `docs/PLAN.md`**

Change the gate 31 row's status cell from `⬜ not started …` to `✅ done` with a one-line summary:
what shipped (`chat-shell.tsx` wrapper, `localStorage` `agent-panel-mode`, `Esc` to collapse,
page hidden via `display:none`), the commit range, and — if Step 5 found it — the scroll-position
caveat. Keep it to the same length as the other done rows. Do **not** touch the spec reference or
gates 32–34.

- [ ] **Step 10: Update `docs/FRONTEND-PLAN.md`**

Add one dated line (2026-09-09) noting that the agent panel gained an expand/fullscreen mode in
gate 31, `chat-shell.tsx` now owns the signed-in layout row, and the mode is a `localStorage`
concept with no library (same as the density toggle). Point to the spec and this plan. Do not
restate the design.

- [ ] **Step 11: Hand off for commit**

Explain: browser walkthrough passed (list any caveat found), docs updated. Files: `docs/PLAN.md`,
`docs/FRONTEND-PLAN.md`. Suggested commit:

```
docs(plan): mark gate 31 (chat fullscreen mode) done

Verified in-browser against the dev stack: expand/collapse, Esc,
localStorage persistence, no route change or refetch, signed-out
unaffected.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XruycPu9FKxDpuCES3GRC6
```

Then stop — gate 31 is complete. Gates 32 (Markdown), 33 (structured tool output), and 34 (cards)
are separate plans.

---

## Self-Review

**Spec coverage** (against "Priority 1 — fullscreen / expand mode → Gate 31"):

| Spec requirement | Task |
|---|---|
| New client component `chat-shell.tsx` wraps `<main>` + `<AgentPanel>`; `layout.tsx` stays a Server Component | Task 1 |
| `mode: "docked" \| "expanded"` owned by `chat-shell.tsx` | Task 2, Step 1 |
| docked = `<main flex-1>` + `<AgentPanel w-64>`; expanded = `<main hidden>` + `<AgentPanel flex-1>` | Task 2, Steps 1 & 3 |
| Page uses `hidden` (`display:none`), mounted not unmounted; no navigation/refetch | Task 2 Step 1; verified Task 3 Steps 3 & 5 |
| Persistence: `localStorage` key `agent-panel-mode`, density-toggle pattern, no flash | Task 2 Step 1 (`mounted` gate); verified Task 3 Step 7 |
| Controls: expand/collapse icon button in panel header next to `X`; `Esc` collapses | Task 2 Steps 2 & 1 |
| Readability when expanded: message column `max-w-3xl` centered | Task 2 Step 4 |
| Out of scope: auto-expand on small screens; any change to what the page routes to | Not in plan — correct |
| Test: toggle → page hidden, nav+header present, conversation intact; toggle back → same scroll, no request; reload → expanded | Task 3 Steps 3–7 |

No spec requirement for gate 31 is unaddressed.

**Placeholder scan:** no "TBD"/"handle edge cases"/"similar to Task N". Every code step has the
actual code. The one genuine unknown — whether `display:none` preserves scroll position in the
target browser — is called out explicitly in Task 3 Step 5 with a defined fallback (record as a
caveat, not a blocker), which is correct because the spec itself lists it as behaviour to verify,
not a guarantee.

**Type consistency:** `ChatMode` is defined once in `chat-mode.ts` and imported everywhere.
`AgentPanel` props (`mode: ChatMode`, `onToggleMode: () => void`) are identical in `chat-shell.tsx`
(call site), `agent-panel.tsx` (`AgentPanel` and `ConnectedAgentPanel` signatures), and
`ExpandToggle`. `readStoredMode` / `nextMode` / `CHAT_MODE_STORAGE_KEY` names match between
`chat-mode.ts` and `chat-shell.tsx`.
