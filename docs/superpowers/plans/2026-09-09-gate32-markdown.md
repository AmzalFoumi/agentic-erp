# Gate 32 — Markdown Rendering for Assistant Text Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assistant text in the chat panel renders as real Markdown (today `**bold**` and `* item`
show as literal characters), using one new dependency, and the same renderer is available for the
prose inside gate 34's cards.

**Architecture:** One new client component,
`frontend/src/components/shell/agent-panel/markdown.tsx`, wraps Vercel's **Streamdown 2.6.0** — a
streaming-hardened drop-in for `react-markdown`. `message-list.tsx` renders each assistant message's
text through `<Markdown>` instead of as a bare string; user messages stay plain text. Two lines are
added to `globals.css` so Tailwind v4 picks up Streamdown's utility classes and animation CSS. The
streaming "still typing" cursor stops being a hand-rolled `<span>` and becomes Streamdown's own
`caret="block"` (same `▍` glyph, positioned at the true end of the streamed text).

**Tech Stack:** Next.js 16 (App Router, `src/` layout, Turbopack), React 19.2.4, Tailwind v4,
`streamdown@2.6.0` (new — pulls `unified` / `remark-gfm` / `rehype-sanitize` / `rehype-harden` /
`marked` / `remend`; no React peer conflict — its peers are `react ^18 || ^19`).

**Spec:** `docs/superpowers/specs/2026-09-09-chatbot-overhaul-design.md` — read "Priority 3 —
Markdown rendering → Gate 32" and the "Hard constraints" section first. Where this plan and the spec
disagree, the spec is right **except** on the library API: the spec was written against Streamdown
v1 and names props (`allowedLinkPrefixes`, `allowedImagePrefixes`) that **do not exist in 2.6.0**.
This plan uses the verified 2.6.0 API (see "Library facts" below).

## Global Constraints

Copied from the spec's "Hard constraints" plus the two constraints the user added when approving
this plan (2026-09-09). Every task's requirements implicitly include this section.

- **Frontend only.** No file outside `frontend/` changes except `docs/PLAN.md` and
  `docs/FRONTEND-PLAN.md` in the final task. No backend, no `agent/`, no `mcp_server/`.
- **No routing changes.** No new routes, no changes to `src/proxy.ts` or
  `src/app/api/agent/[...path]/route.ts`.
- **No auth / permission / ThunderID changes.** No new scopes, no Console changes, no token
  handling. `deploy/aisle-box/` is not touched.
- **No hardcoded design values in components.** `markdown.tsx` uses token utilities only
  (`text-primary`, `font-mono`, `text-sm`, the `gap-stack` / `p-section` family, `rounded-(--radius)`).
  Any value that is not already a token — a new colour, a new spacing step, a prose max-width — is
  added to `globals.css` as a `--` custom property first and referenced by name. The reason: a
  future UI overhaul should touch one file. If you find yourself typing a hex code, an `oklch(...)`,
  or a raw `rem` in a component, stop and add a token.
- **One new dependency, and it is `streamdown` only.** Not `@streamdown/code`, `@streamdown/math`,
  `@streamdown/mermaid`, or `@streamdown/cjk` — the ERP chat has no need for syntax highlighting,
  LaTeX, diagrams, or CJK width handling, and each is a separate install with its own `@source`
  line and its own bundle cost.
- **The ESLint architecture rules hold.** `markdown.tsx` is a component: it must not import from
  `openapi-fetch`, `@/lib/api/schema*`, or `server-only`, and must not call `fetch`. It imports
  `streamdown` and `@/lib/utils` only. Run `npm run lint` after every task.

Project working-agreement constraints that apply here:

- **The developer runs `npm install` / `npm run *` / `npx` / `git`.** This plan tells you which
  commands to give the developer and what output to expect; you do not run them yourself. In
  particular **you do not run `npm install streamdown`** — you hand the developer that command and
  wait for them to confirm `package.json` and the lockfile changed.
- **Browser MCP (chrome-devtools) is allowed only after the developer has `npm run dev` running and
  says continue.** The dev stack and ThunderID were up earlier this session; re-confirm before
  Task 2. Test user: `amzal` / password `12345`.
- **Stop-gate discipline:** each task ends by explaining what changed, listing files touched, and
  handing off for a manual `git commit`. Do not push.
- **Commit message trailers:** end every commit message with
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01XruycPu9FKxDpuCES3GRC6`.

## The frontend has no test runner — how "test" works here

Confirmed at gate 31 and reconfirmed by the user for this gate: `frontend/` has no vitest / jest /
MSW. There are **no `*.test.tsx` files to write.** Each task is verified by, in order:

1. `npx tsc --noEmit` — clean. This is the real check that our use of Streamdown's API matches its
   shipped types.
2. `npm run lint` — clean (ESLint, including the restricted-import architecture rules).
3. `npm run build` — succeeds. `export const dynamic = "force-dynamic"` in `layout.tsx` already
   makes every route per-request, so the build does not prerender.
4. A scripted **chrome-devtools MCP walkthrough** (Task 2) — the behavioural check.

## Library facts — Streamdown 2.6.0 (verified 2026-09-09 from the published tarball)

Do not trust older docs or the library's `main` branch — both describe a different (v1, or unreleased
v3) API. These are read from `streamdown@2.6.0`'s `dist/index.d.ts` and compiled source:

- **Content is a string child:** `<Streamdown>{markdownString}</Streamdown>`.
- **Props that exist:** `children`, `className`, `components` (react-markdown-style element-override
  map; also `inlineCode` for inline `` `code` `` specifically), `disallowedElements`,
  `allowedElements`, `allowElement`, `unwrapDisallowed`, `urlTransform`, `remarkPlugins`,
  `rehypePlugins`, `skipHtml`, `parseIncompleteMarkdown` (**default `true`**), `mode` (**default
  `"streaming"`**), `caret` (`"block"` → ` ▍` U+258B; `"circle"` → ` ●`), `isAnimating` (**default
  `false`**), `controls` (**default `true`**), `lineNumbers` (**default `true`**),
  `codeBlockMaxHeight` (default `400`), `tableMaxHeight` (default `300`), `animated`, `linkSafety`,
  `translations`, `icons`, `prefix`, `plugins`.
- **Props the spec named that DO NOT EXIST in 2.6.0:** `allowedLinkPrefixes`, `allowedImagePrefixes`,
  `defaultOrigin`. Link/image restriction in 2.6.0 is done via `disallowedElements` / `urlTransform`
  / the built-in hardening pipeline, not a prefix prop.
- **Links are already safe-ish by default:** every `<a>` Streamdown renders carries
  `rel="noreferrer" target="_blank"` (confirmed in compiled source), and the default rehype pipeline
  includes `rehype-sanitize` + `rehype-harden`, which strip `javascript:` / `data:` script vectors
  and disallowed tags (`<script>`, `<iframe>`, event-handler attributes). The hardening plugin's
  *prefix allowlists* default to `"*"` (permissive), but the *scheme* and *tag* sanitization is
  active. For this gate that is sufficient: assistant text is model output about internal inventory,
  not attacker-controlled input. We additionally block images as a product choice (below).
- **The caret:** when `caret="block"` and `isAnimating` is true and the last block is not settled,
  Streamdown sets `--streamdown-caret: "▍"` inline on the last block and renders it through the
  Tailwind class `after:content-[var(--streamdown-caret)]`. **That class only exists if the `@source`
  directive (Task 1, Step 2) is present and its path is correct** — otherwise the caret is invisible
  and so is most of Streamdown's spacing.
- **Code highlighting / Mermaid / math / CJK are opt-in** via `plugins={{ code, mermaid, math, cjk }}`
  from separate packages. We pass no `plugins`, so fenced code renders as a plain scrollable
  `<pre>` block with a copy button and (by default) line numbers.
- **`styles.css`** (53 lines) provides the keyframes (`sd-fadeIn` etc.) and the `::marker` fade
  rule. It must be imported; the utility classes come from `@source`.

---

## File Structure

| File | New / Modified | Responsibility |
|---|---|---|
| `frontend/src/components/shell/agent-panel/markdown.tsx` | **New** | Client component. `<Markdown>{string}</Markdown>` → styled React via Streamdown. Owns the one `components` override (link styling), the image block, the caret wiring, and the container class. The single place Streamdown is imported. Reused by gate 34's cards. |
| `frontend/src/app/globals.css` | Modified (2 lines added near the top) | `@import "streamdown/styles.css";` and `@source "../../node_modules/streamdown/dist/*.js";` so Tailwind v4 emits Streamdown's utility classes and ships its animation CSS. |
| `frontend/src/components/shell/agent-panel/message-list.tsx` | Modified | Assistant branch renders `<Markdown>` + Streamdown's caret instead of `{text}` + the hand-rolled blink `<span>`. User branch unchanged. |
| `frontend/package.json` + `package-lock.json` | Modified (developer runs `npm install streamdown`) | Adds `streamdown@^2.6.0`. |

`grep` for where assistant text renders returns only `message-list.tsx` (`textOf` + the bubble).
`success-card.tsx` prints `String(part.output)` in a `<div>` — that is a tool-result string, not
model prose, and is **out of scope** for this gate (it becomes a real card at gate 34).

---

## Task 1: add Streamdown, wire `globals.css`, build `markdown.tsx`, render it in `message-list.tsx`

**Deliverable:** assistant replies in the chat panel render as Markdown — bold, lists, tables,
inline code, code fences — with a correctly-positioned streaming caret; user messages look exactly
as before; type-checks, lints, builds.

**Files:**
- Create: `frontend/src/components/shell/agent-panel/markdown.tsx`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/components/shell/agent-panel/message-list.tsx`
- Modify (developer): `frontend/package.json`, `frontend/package-lock.json`

**Interfaces:**
- Produces: `markdown.tsx` exports
  `export function Markdown({ children, className }: { children: string; className?: string }): JSX.Element`.
  `children` is a Markdown source string. `className` is merged onto Streamdown's root and is how a
  caller (gate 34 card) tightens spacing.
- Consumes: `cn` from `@/lib/utils`; `Streamdown` from `streamdown`.

- [ ] **Step 1: Hand the developer the install command**

Give the developer, to run from `frontend/`:

```bash
npm install streamdown
```

Expected: `package.json` gains `"streamdown": "^2.6.0"` (or a later 2.x) under `dependencies`, and
`package-lock.json` changes. Ask them to paste the new `package.json` dependency line so you can
confirm the major version is `2`. If npm resolves a `3.x`, **stop** — the 3.x API differs (it splits
code/math/mermaid into `plugins`); this plan is written for 2.x. Pin `"streamdown": "~2.6.0"` in
that case and note it for the reviewer.

Do not proceed to Step 2 until the developer confirms the install succeeded.

- [ ] **Step 2: Add the two lines to `frontend/src/app/globals.css`**

The file starts with three `@import` lines (`tailwindcss`, `tw-animate-css`, `shadcn/tailwind.css`)
then `@custom-variant dark (...)`. Insert Streamdown's import as a fourth `@import`, and the
`@source` directive immediately after the import block:

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "streamdown/styles.css";

/*
 * Streamdown ships its prose styling as Tailwind utility classes baked into its
 * compiled JS (dist/*.js), not as a stylesheet. This @source line tells
 * Tailwind v4 to scan that file so those classes — including the streaming
 * caret's `after:content-[var(--streamdown-caret)]` — actually get generated.
 *
 * The path is relative from THIS file (frontend/src/app/globals.css) to
 * frontend/node_modules. `../../` climbs src/app → src → frontend. If Streamdown
 * renders as an unstyled wall of text in the browser, this path is wrong: count
 * the directories again.
 */
@source "../../node_modules/streamdown/dist/*.js";

@custom-variant dark (&:is(.dark *));
```

Do not touch anything else in `globals.css` — not `@theme inline`, not `:root`, not the density
blocks, not `@layer utilities`.

Note: no new `--` token is needed for this task. `markdown.tsx` uses only utilities that already
resolve (`text-sm`, `text-primary`, `font-mono`, `leading-relaxed`, `max-w-none`). If Task 1's
walkthrough (in Task 2) shows a value you cannot express with an existing token, that is when you
add one here — not before.

- [ ] **Step 3: Write `frontend/src/components/shell/agent-panel/markdown.tsx`**

```tsx
"use client";

import { Streamdown } from "streamdown";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/**
 * Markdown rendering for assistant prose. Gate 32.
 *
 * Wraps Streamdown (a streaming-hardened drop-in for react-markdown): it parses
 * incomplete Markdown without crashing — a half-streamed ``` fence or | table |
 * renders as far as it got and completes itself as more tokens arrive.
 *
 * Styling: Streamdown's built-in classes read the same shadcn CSS variables
 * this project maps in globals.css (--foreground, --primary, --border,
 * --radius, --muted...), so headings, lists, tables, blockquotes and code
 * inherit the design system, dark mode, and both densities for free. The only
 * override is link colour (to match every other link in the app) and the
 * container type size. No colours, radii or raw lengths live here — see the
 * plan's Global Constraints.
 *
 * Safety: Streamdown's default pipeline (rehype-sanitize + rehype-harden)
 * strips <script>/<iframe>/event handlers and javascript:/data: script URLs;
 * every link it renders already gets rel="noreferrer" target="_blank". We also
 * drop images entirely — the agent answers about internal stock, it has no
 * reason to embed remote media, and an <img> is the one easy exfiltration
 * pixel that survives sanitization.
 *
 * Reused by gate 34's response cards for any model prose inside a card; pass
 * `className` to tighten the spacing there.
 */

const components = {
  a: ({ className, ...props }: ComponentProps<"a">) => (
    <a
      {...props}
      // target/rel are already set by Streamdown; repeating them is harmless
      // and makes the intent obvious at the call site.
      target="_blank"
      rel="noreferrer"
      className={cn("text-primary hover:underline", className)}
    />
  ),
};

export function Markdown({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  return (
    <Streamdown
      className={cn(
        // `max-w-none` because the chat bubble is already the width constraint;
        // Streamdown's default prose max-width would double-constrain it.
        "text-sm leading-relaxed max-w-none",
        className,
      )}
      components={components}
      disallowedElements={["img"]}
      unwrapDisallowed
      caret="block"
    >
      {children}
    </Streamdown>
  );
}
```

Notes for the implementer:
- **`isAnimating` is not set here.** It is passed by `message-list.tsx` per-message (only the last
  assistant message, only while streaming). But `Markdown`'s public signature is
  `{ children, className }` only — so `message-list.tsx` cannot pass `isAnimating` through unless we
  add it. **Add `isAnimating` to the signature** as an optional boolean and forward it:

```tsx
export function Markdown({
  children,
  className,
  isAnimating,
}: {
  children: string;
  className?: string;
  isAnimating?: boolean;
}) {
  return (
    <Streamdown
      className={cn("text-sm leading-relaxed max-w-none", className)}
      components={components}
      disallowedElements={["img"]}
      unwrapDisallowed
      caret="block"
      isAnimating={isAnimating}
    >
      {children}
    </Streamdown>
  );
}
```

- If `tsc` complains that the `components` map's `a` value is not assignable to Streamdown's
  `Components["a"]`, widen the parameter type to
  `ComponentProps<"a"> & { node?: unknown }` — Streamdown passes a `node` prop that
  `ComponentProps<"a">` does not include.
- Do **not** add `remarkPlugins` / `rehypePlugins` — GFM (tables, strikethrough, task lists) is on
  by default in Streamdown, and touching `rehypePlugins` replaces the whole default pipeline
  including the hardening.

- [ ] **Step 4: Render `<Markdown>` in `message-list.tsx`**

Current file (whole thing):

```tsx
"use client";

import type { UIMessage } from "@ai-sdk/react";

function textOf(message: UIMessage): string {
  return message.parts
    .filter((part) => part.type === "text")
    .map((part) => (part as { text: string }).text)
    .join("");
}

export function MessageList({
  messages,
  isStreaming,
}: {
  messages: UIMessage[];
  isStreaming: boolean;
}) {
  return (
    <div className="flex flex-col gap-stack">
      {messages.map((message, index) => {
        const text = textOf(message);
        if (!text) return null;
        const isLast = index === messages.length - 1;
        return (
          <div
            key={message.id}
            className={
              message.role === "user"
                ? "self-end rounded-(--radius) bg-primary px-3 py-2 text-sm text-primary-foreground"
                : "self-start rounded-(--radius) bg-secondary px-3 py-2 text-sm text-secondary-foreground"
            }
          >
            {text}
            {isLast && isStreaming && message.role === "assistant" && (
              <span className="animate-blink" aria-hidden="true">
                ▍
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

Replace it with:

```tsx
"use client";

import type { UIMessage } from "@ai-sdk/react";

import { Markdown } from "./markdown";

function textOf(message: UIMessage): string {
  return message.parts
    .filter((part) => part.type === "text")
    .map((part) => (part as { text: string }).text)
    .join("");
}

export function MessageList({
  messages,
  isStreaming,
}: {
  messages: UIMessage[];
  isStreaming: boolean;
}) {
  return (
    <div className="flex flex-col gap-stack">
      {messages.map((message, index) => {
        const text = textOf(message);
        if (!text) return null;
        const isLast = index === messages.length - 1;
        const isAssistant = message.role === "assistant";
        const streamingHere = isLast && isStreaming && isAssistant;
        return (
          <div
            key={message.id}
            className={
              message.role === "user"
                ? "self-end rounded-(--radius) bg-primary px-3 py-2 text-sm text-primary-foreground"
                : "self-start rounded-(--radius) bg-secondary px-3 py-2 text-sm text-secondary-foreground"
            }
          >
            {isAssistant ? (
              <Markdown isAnimating={streamingHere}>{text}</Markdown>
            ) : (
              text
            )}
          </div>
        );
      })}
    </div>
  );
}
```

What changed and why:
- The hand-rolled `<span className="animate-blink">▍</span>` is **gone**. Streamdown's `caret="block"`
  (set in `markdown.tsx`) renders the same `▍` glyph, but at the true end of the last text block
  and only while `isAnimating` — which we pass as `streamingHere`. The `animate-blink` utility in
  `globals.css` stays (the thinking indicator does not use it, but `@layer utilities` is cheap and
  removing it is a separate cleanup — leave it).
- User messages render `text` exactly as before — a raw string node, no Markdown parsing. This was
  the user's explicit choice (assistant-only).
- `text-sm` now appears both on the bubble `<div>` and inside `markdown.tsx`. That is deliberate
  redundancy: the bubble keeps its size for the user branch, and `markdown.tsx` is
  self-contained for the gate 34 card reuse. It resolves to the same value; there is no conflict.

- [ ] **Step 5: Give the developer the verification commands**

From `frontend/`:

```bash
npx tsc --noEmit
npm run lint
npm run build
```

Expected: all three clean. Specifically:
- `tsc` proves our `<Streamdown>` props and the `components` map match `streamdown@2.6.0`'s types.
  A failure here is a real API mismatch — fix the code, do not cast it away, except the one known
  `node`-prop widening noted in Step 3.
- `lint` — the restricted-import rule should be quiet: `markdown.tsx` imports `streamdown` (not on
  the restricted list) and `@/lib/utils`. If it flags `streamdown`, the rule config is stricter
  than expected — stop and report, do not edit `eslint.config.mjs`.
- `build` — if it fails resolving `streamdown/styles.css`, the `@import` in `globals.css` is
  mis-ordered (it must be with the other `@import`s, before any non-import rule).

- [ ] **Step 6: Hand off for commit**

Explain: assistant chat text now renders as Markdown via Streamdown 2.6.0 (`markdown.tsx`, one new
dep); `message-list.tsx` routes assistant text through it and drops the hand-rolled streaming
cursor in favour of Streamdown's caret; `globals.css` gains the import + `@source` line Streamdown
needs under Tailwind v4. User messages are untouched. No backend / auth / routing changes. Files:
`markdown.tsx` (new), `message-list.tsx`, `globals.css`, `package.json`, `package-lock.json`.
Suggested commit:

```
feat(chat): render assistant messages as Markdown

Gate 32. New markdown.tsx wraps Streamdown 2.6.0 (streaming-hardened
react-markdown drop-in); message-list.tsx renders assistant text through
it and uses Streamdown's caret instead of the hand-rolled blink span.
User messages stay plain text. globals.css gains the styles.css import
and the @source directive Tailwind v4 needs to emit Streamdown's classes.
Images are dropped; links keep rel="noreferrer" target="_blank".
Frontend only.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XruycPu9FKxDpuCES3GRC6
```

---

## Task 2: browser walkthrough verification + docs

**Deliverable:** Markdown rendering is confirmed in a real browser against the running dev stack,
including the streaming and half-fence cases; `docs/PLAN.md` and `docs/FRONTEND-PLAN.md` record the
gate as done.

**Files:**
- Modify: `docs/PLAN.md` (gate 32 row)
- Modify: `docs/FRONTEND-PLAN.md` (extend the gate 31 amendment block, or add a dated line)

**Prerequisite:** confirm with the developer that `npm run dev` is up on `http://localhost:3000` and
the agent + ThunderID stack is running, and that they say continue. Then use chrome-devtools MCP.

- [ ] **Step 1: Sign in**

Navigate to `http://localhost:3000`. If not signed in, sign in as `amzal` / `12345` through the
ThunderID flow (accept the self-signed cert warning if it appears — expected, documented in
`CLAUDE.md`).

- [ ] **Step 2: A formatted answer renders as Markdown**

On `/products`, open the chat panel and send: `What is low on stock? Reply with a short intro
sentence, then a bullet list of the products, then a markdown table with columns Product, On hand,
Reorder level.`

Expected once the reply completes:
- The intro sentence is a normal paragraph.
- The bullet list renders as an actual `<ul>` with disc markers — **not** literal `* ` at the start
  of each line.
- The table renders as a real bordered `<table>` with a header row. In the 256px docked panel it
  scrolls horizontally inside its own box (Streamdown wraps tables in an
  overflow container, `tableMaxHeight` 300) — the panel itself must **not** grow a horizontal
  scrollbar or push the layout wider.
- Any `**bold**` or `` `inline code` `` in the reply shows as bold / monospace, not literal
  asterisks or backticks.
- Take a screenshot for the record.

- [ ] **Step 3: The same answer in the expanded panel**

Click the expand button (gate 31). The reply should reflow to the wider `max-w-3xl` column; the
table now has room and should not need to scroll. No console errors on resize
(`list_console_messages`).

- [ ] **Step 4: A code fence renders**

Send: `Show me a small example JSON object for a product, in a fenced code block.`

Expected: a `<pre>` block with a monospace body, a copy button in its header, and (default) line
numbers. It has its own vertical scroll if long (`codeBlockMaxHeight` 400). Clicking copy does not
throw.

- [ ] **Step 5: A half-streamed fence does not crash (the key streaming test)**

Send: `Write a 12-line YAML config for a supermarket product, in a fenced code block, and explain
each line after.` Watch the panel **during** streaming, before the reply finishes.

Expected: while the ``` fence is open and only partially streamed, the panel keeps rendering — the
partial code block shows what has arrived so far, the trailing `▍` caret sits at the end of it, and
there is **no** React error overlay and **no** entry in `list_console_messages`. When the stream
completes, the block closes cleanly and the caret disappears.

- [ ] **Step 6: Links are sanitized and open safely**

Send: `Reply with exactly this markdown and nothing else: [click me](javascript:alert(1)) and
[docs](https://example.com) and <script>alert(2)</script> and <img src="https://example.com/x.png">`

Expected:
- `[click me](javascript:alert(1))` renders as text or a dead link — the `href` is stripped or
  neutralised, clicking it does nothing, no `alert`.
- `[docs](https://example.com)` renders as a real link, `text-primary`, and inspecting it
  (`evaluate_script` on the anchor) shows `target="_blank"` and `rel` containing `noreferrer`.
- The `<script>` tag does not execute (no `alert(2)`) and renders as inert text or nothing.
- The `<img>` does **not** appear — `disallowedElements={["img"]}` drops it. No network request
  fires for `example.com/x.png` (`list_network_requests`).
- `list_console_messages` is clean of security or React warnings.

- [ ] **Step 7: Dark mode and comfortable density**

Toggle the theme to dark (header control): the rendered Markdown — text, table borders, code block
background, blockquote bar — recolours to the dark tokens, nothing stays light, contrast is
readable. Toggle density to comfortable: spacing between paragraphs / list items / the table
loosens with the rest of the UI (Streamdown's classes are token-based, so this should follow
automatically — if a block stays visually "dense" while everything around it loosened, note it).

- [ ] **Step 8: User messages are still plain**

Send a user message containing `**not bold** and * not a bullet`. It must render as literal text in
the user bubble — no parsing. (Confirms the assistant-only branch.)

- [ ] **Step 9: Update `docs/PLAN.md`**

Change the gate 32 row's status cell from `⬜ not started …` to `✅ done 2026-09-09` with a one-line
summary in the same style as the other done rows: what shipped (`markdown.tsx` wrapping Streamdown
2.6.0, `message-list.tsx` routes assistant text through it, `globals.css` `@source` line, images
dropped, Streamdown caret replaces the hand-rolled one), the commit range, and any caveat Step 7 or
Step 2 turned up. Do **not** touch the gates 33 / 34 rows or the spec-reference row.

- [ ] **Step 10: Update `docs/FRONTEND-PLAN.md`**

Extend the "Amended 2026-09-09 (Gate 31)" block (or add a sibling dated line for Gate 32): note
that assistant chat text now renders as Markdown via `streamdown@2.6.0`, the wrapper is
`components/shell/agent-panel/markdown.tsx` and is the renderer gate 34's cards will reuse, and
`globals.css` gained a `@source` directive for it. Point to the spec's "Priority 3" section and this
plan. One paragraph, no restated design.

- [ ] **Step 11: Hand off for commit**

Explain: browser walkthrough passed (list any caveat), docs updated. Files: `docs/PLAN.md`,
`docs/FRONTEND-PLAN.md`. Suggested commit:

```
docs(plan): mark gate 32 (markdown rendering) done

Verified in-browser: bold/lists/tables/inline code/code fences render,
a half-streamed fence does not crash, javascript: links and <script> are
neutralised, <img> is dropped, dark mode and comfortable density follow.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XruycPu9FKxDpuCES3GRC6
```

Then stop — gate 32 is complete. Gate 33 (structured tool-output contract) and gate 34 (response
cards) are separate plans; gate 33's plan also needs the `agent/mcp_client.py` change recorded in
`memory/project_chatbot_overhaul.md`.

---

## Self-Review

**Spec coverage** (against "Priority 3 — Markdown rendering → Gate 32"):

| Spec requirement | Task |
|---|---|
| New component `components/shell/agent-panel/markdown.tsx`, used by `MessageList` and reusable by cards | Task 1, Step 3; signature takes `className` for card reuse |
| One new frontend dependency, developer runs `npm install` | Task 1, Step 1 |
| Library decided at implementation after verifying current versions + Tailwind v4 compat | Done: Streamdown 2.6.0, verified against the published tarball; "Library facts" section |
| Text parts render as Markdown instead of `{text}` | Task 1, Step 4 |
| Override styling to design tokens (Figtree / IBM Plex Mono, `--radius`) | Task 1, Step 3 — Streamdown inherits the mapped shadcn tokens; only link colour is overridden; Global Constraint forbids hardcoded values |
| Code blocks in mono | Default — Streamdown code blocks are monospace; verified Task 2 Step 4 |
| Links open in new tab with `rel="noreferrer"`, safe schemes only | Task 1 Step 3 (`a` override + Streamdown default) ; verified Task 2 Step 6 |
| Test: `**bold**`, bullet lists, tables, inline code, code fences render | Task 2 Steps 2 & 4 |
| Test: a half-streamed fence does not crash | Task 2 Step 5 |
| Test: links are sanitized | Task 2 Step 6 |
| Test: renders correctly in dark mode and both densities | Task 2 Step 7 |
| Scope: frontend only, `components/shell/agent-panel/`, no backend / `agent/` | Global Constraints; only `globals.css` + `message-list.tsx` + the new file change |

The spec also says "also the renderer for prose inside gate 34's cards" — met by `Markdown`
accepting `className` and having no chat-specific assumptions. No gate-32 spec requirement is
unaddressed. The spec's `allowedLinkPrefixes` / `allowedImagePrefixes` wording is superseded by the
verified 2.6.0 API (documented in "Library facts" and the plan header).

**Placeholder scan:** no "TBD" / "handle edge cases" / "similar to Task N". Every code step has the
full file or the full replacement. The one genuine open decision — whether an existing token covers
every spacing need or a new `--` token is required — is bounded: Global Constraints + Task 1 Step 2
say add it to `globals.css` when the walkthrough proves it necessary, and the walkthrough (Task 2
Step 7) is the check.

**Type consistency:** `Markdown`'s signature is `{ children: string; className?: string;
isAnimating?: boolean }` — defined once in Step 3, consumed once in Step 4
(`<Markdown isAnimating={streamingHere}>{text}</Markdown>`). `streamingHere` is a `boolean`.
`components` is a module-level const in `markdown.tsx`, not exported. No name appears in one task
with a different spelling in another.
