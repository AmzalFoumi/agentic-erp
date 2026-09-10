# Gate 34 — Response Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render structured MCP read-tool output in the agent chat panel as typed visual cards instead of the model re-typing rows as prose, plus one prompt line telling the model not to re-type.

**Architecture:** Frontend-only except one string. A card registry maps `tool-<name>` → a React component; `MessageList` iterates every part of each assistant message in order and renders a card for each read-tool output part, text parts through the existing `<Markdown>`. Cards are hand-built from the existing `ui/` primitives and design tokens, share a `ChatCard` shell and a responsive `ChatCardTable`, and fall back to a generic `FallbackCard` for any unregistered or unparseable output. The write-side cards (`ToolCallCard`, `SuccessCard`) are re-parented onto the same shell. The one agent change is a sentence appended to `INSTRUCTIONS` in `agent/conversation.py`.

**Tech Stack:** Next.js 16 (App Router, Turbopack), React 19.2, Tailwind v4, TypeScript, `@ai-sdk/react` ^4 / `ai` ^7 (`useChat`, `UIMessage`), Streamdown 2.6.0 (via the existing `Markdown` wrapper). Agent side: Python 3.12, pytest, pydantic-ai.

**Spec:** `docs/superpowers/specs/2026-09-09-chatbot-overhaul-design.md` — section **"Gate 34 — response cards + prompt line"**. Read it alongside this plan. Reload persistence and the parked items R3/R4 are **out of scope** — they are gate 34b.

> **Execution status (2026-09-10, COMPLETE):** SDD run finished on `feat/client/chatbot`.
> All 8 tasks done (`88b04ae..809661f`, plus follow-up `d078ddd`), browser walkthrough passed,
> `tsc`/`lint` green. Reload persistence and parked items R3/R4 are gate 34b (not started).
> SDD ledger: `.superpowers/sdd/2026-09-10-gate34-response-cards/progress.md` (git-ignored).

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the spec's "Hard constraints" block and the project's `CLAUDE.md` / `frontend/CLAUDE.md`.

- **No routing changes.** No new routes, no route renames, no changes to `frontend/src/proxy.ts` or `frontend/src/app/api/agent/[...path]/route.ts`.
- **No auth / permission / ThunderID changes.** No new scopes, no Console changes, no token handling changes. `deploy/aisle-box/` is not touched.
- **The only backend/agent change in this gate is one sentence appended to `INSTRUCTIONS` in `agent/conversation.py`.** No change to `services/`, `authn/`, `api/`, `core/`, `mcp_server/`, or any type, import, or function in `agent/`. The `INSTRUCTIONS` change adds no import and changes no type — it is a plain string literal.
- **The one architecture rule holds.** `agent/` isolation cluster untouched (the `INSTRUCTIONS` string is not a framework type).
- **Loopback binding stays.** `agent/app.py`'s `HOST = "127.0.0.1"` is not touched.
- **Money is a JSON string, never a float.** Format every money value with `formatMoney` from `frontend/src/lib/format.ts`. Never call `Number()` / `parseFloat` on a money field.
- **No hardcoded design values in components.** Use Tailwind token utilities (`bg-card`, `border-border`, `text-muted-foreground`, `rounded-(--radius)`, `gap-stack`, `p-section`, the `stock-*` colours, `tabular-nums`) and the `format.ts` helpers. If a genuinely new token is needed it goes in `frontend/src/app/globals.css` under **both** `:root` and `.dark` — never inline. None is expected.
- **Frontend has no test runner.** `npx tsc --noEmit` and `npm run lint` (run from `frontend/`) are the gate. A typed fixture file per card is the shape contract that `tsc` enforces. Final render verification is the browser walkthrough in the last task.
- **ESLint architecture rules must stay green.** Only `src/lib/api/**` may call `fetch` or construct an API client; components must not import `server-only`. Cards do neither.
- **No tool name is hardcoded outside the card registry** (matches the existing Global Constraint comment in `use-panel-state.ts`).
- **`frontend/src/lib/api/mcp-types.d.ts` and `mcp-schema.json` are generated — never hand-edit them.** Cards import types from `mcp-types.d.ts`.
- **No new npm or pip dependencies.** If a task appears to need one, stop and raise it.
- **Branch:** `feat/client/chatbot`. Commit after every task. Do **not** push. Commit-message trailer, verbatim:

  ```text
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01XruycPu9FKxDpuCES3GRC6
  ```

---

## File Structure

**New — all under `frontend/src/components/shell/agent-panel/`:**

| File | Responsibility |
|---|---|
| `chat-mode-context.tsx` | `ChatModeContext` + `useChatMode()` — carries the panel's `"docked" \| "expanded"` mode down to cards without prop-drilling. |
| `cards/chat-card.tsx` | `ChatCard` — the shared card shell (border, `bg-card`, padding, title slot, optional header-right slot). |
| `cards/chat-card-table.tsx` | `ChatCardTable` — a small typed table that renders as a real `<table>` when expanded and as stacked label/value blocks when docked. Row cap + "view all" overflow link. |
| `cards/parse-tool-output.ts` | `parseToolOutput(output: unknown): unknown` — accepts an already-parsed object or a JSON string; never throws. |
| `cards/card-error-boundary.tsx` | `CardErrorBoundary` — class component; a card that throws despite its guard renders the `FallbackCard` instead of crashing the transcript. |
| `cards/fallback-card.tsx` | `FallbackCard` — collapsible key/value + raw JSON for any unregistered or unparseable output. |
| `cards/registry.tsx` | `CARD_REGISTRY` map + `renderToolCard(part)` — the one place a `tool-<name>` string maps to a component. |
| `cards/product-cards.tsx` | `ProductListCard` (`list_products`), `ProductCard` (`get_product`, `get_product_by_sku`). |
| `cards/inventory-cards.tsx` | `SpoilageCard` (`check_spoilage_risk`), `LotsCard` (`list_product_lots`). |
| `cards/purchasing-cards.tsx` | `ReorderBundlesCard` (`suggest_reorder_bundles`), `PendingDraftsCard` (`list_pending_drafts`), `PurchaseOrdersCard` (`list_purchase_orders`). |
| `cards/fixtures.ts` | One typed fixture constant per registered card, each annotated with its `MCPToolOutputs[...]` type. `tsc` checks these. |

**Modified:**

| File | Change |
|---|---|
| `frontend/src/components/shell/agent-panel/message-list.tsx` | Iterate every part of each assistant message in order; render read-tool cards inline; drop the `if (!text) return null` early-return. |
| `frontend/src/components/shell/agent-panel.tsx` | Wrap `ConnectedAgentPanel`'s body in `<ChatModeContext.Provider value={mode}>`. No other change. |
| `frontend/src/components/shell/agent-panel/tool-call-card.tsx` | Re-parent onto `ChatCard`. Behaviour unchanged. |
| `frontend/src/components/shell/agent-panel/success-card.tsx` | Re-parent onto `ChatCard`. Behaviour unchanged. |
| `agent/conversation.py` | Append one sentence to `INSTRUCTIONS`. |
| `agent/tests/test_app.py` *(or a new `agent/tests/test_instructions.py`)* | One assertion that the new guidance substring is present. |
| `docs/PLAN.md`, `docs/FRONTEND-PLAN.md`, `docs/DEPLOY-PLAN.md`, the spec | Mark gate 34 done; record what it owes the box (nothing). |

**Card component contract (used by every card task):**

```typescript
// A card receives the raw part.output (unknown) and renders itself.
// It parses + guards internally and returns <FallbackCard output={output} />
// on any shape mismatch — it never throws.
export type ToolCard = (props: { output: unknown }) => React.ReactNode;
```

---

### Task 1: Card infrastructure — shell, registry, fallback, mode context, MessageList rewire

**Files:**
- Create: `frontend/src/components/shell/agent-panel/chat-mode-context.tsx`
- Create: `frontend/src/components/shell/agent-panel/cards/chat-card.tsx`
- Create: `frontend/src/components/shell/agent-panel/cards/parse-tool-output.ts`
- Create: `frontend/src/components/shell/agent-panel/cards/card-error-boundary.tsx`
- Create: `frontend/src/components/shell/agent-panel/cards/fallback-card.tsx`
- Create: `frontend/src/components/shell/agent-panel/cards/registry.tsx`
- Modify: `frontend/src/components/shell/agent-panel/message-list.tsx`
- Modify: `frontend/src/components/shell/agent-panel.tsx`

**Interfaces:**
- Consumes: `ToolUIPart` from `./use-panel-state` (`{ type: string; toolCallId: string; state: string; input?: Record<string,unknown>; output?: unknown; approval?: {...} }`); `Markdown` from `./markdown`; `UIMessage` from `@ai-sdk/react`; `cn` from `@/lib/utils`; `ChatMode` from `../chat-mode`.
- Produces:
  - `useChatMode(): ChatMode` and `ChatModeContext` (default `"docked"`) — `chat-mode-context.tsx`
  - `ChatCard({ title, headerRight?, children }): React.ReactNode` — `cards/chat-card.tsx`
  - `parseToolOutput(output: unknown): unknown` — `cards/parse-tool-output.ts`
  - `CardErrorBoundary({ fallback, children }): React.ReactNode` — `cards/card-error-boundary.tsx`
  - `FallbackCard({ output }: { output: unknown }): React.ReactNode` — `cards/fallback-card.tsx`
  - `CARD_REGISTRY: Record<string, ToolCard>` and `renderToolCard(part: ToolUIPart): React.ReactNode` — `cards/registry.tsx` (registry is **empty** after this task; every output renders `FallbackCard`)

- [ ] **Step 1: `chat-mode-context.tsx`**

```tsx
"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { ChatMode } from "../chat-mode";

/**
 * Carries the panel's docked/expanded mode to the response cards. The panel
 * already knows its mode (chat-shell.tsx passes it to AgentPanel); this context
 * hands it to cards nested inside MessageList without threading a prop through
 * every layer. Default "docked" — the narrow layout — so a card rendered
 * outside a provider (a test, a stray mount) degrades to the safe compact form.
 */
const ChatModeContext = createContext<ChatMode>("docked");

export function ChatModeProvider({
  mode,
  children,
}: {
  mode: ChatMode;
  children: ReactNode;
}) {
  return <ChatModeContext.Provider value={mode}>{children}</ChatModeContext.Provider>;
}

export function useChatMode(): ChatMode {
  return useContext(ChatModeContext);
}
```

- [ ] **Step 2: `cards/chat-card.tsx`**

```tsx
"use client";

import type { ReactNode } from "react";

/**
 * The shared shell for every response card (read-side cards, and — after the
 * restyle task — the approval and success cards too). One border, one surface,
 * one title treatment, so the chat reads as one system rather than a pile of
 * differently-drawn boxes.
 *
 * No colours, radii, or lengths live here beyond token utilities — see the
 * plan's Global Constraints.
 */
export function ChatCard({
  title,
  headerRight,
  children,
}: {
  title: string;
  headerRight?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-(--radius) border border-border bg-card p-3 text-sm">
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-xs font-semibold uppercase text-muted-foreground">{title}</div>
        {headerRight != null && (
          <div className="shrink-0 text-xs text-muted-foreground tabular-nums">{headerRight}</div>
        )}
      </div>
      {children}
    </div>
  );
}
```

- [ ] **Step 3: `cards/parse-tool-output.ts`**

```ts
/**
 * Normalise a tool part's `output` into something a card can inspect.
 *
 * After gate 33 the streamed `tool-output-available.output` is already a JSON
 * object/array (pydantic-ai's `tool_return_output` passes a dict through
 * unchanged). But `success-card.tsx` shows the wire has also carried a JSON
 * *string* in the past, so this tolerates both. It never throws: an
 * unparseable string comes back as-is and the caller's type guard rejects it,
 * routing to <FallbackCard>.
 */
export function parseToolOutput(output: unknown): unknown {
  if (typeof output === "string") {
    try {
      return JSON.parse(output);
    } catch {
      return output;
    }
  }
  return output;
}
```

- [ ] **Step 4: `cards/card-error-boundary.tsx`**

```tsx
"use client";

import { Component, type ReactNode } from "react";

/**
 * Belt and braces. Every card already parses defensively and returns
 * <FallbackCard> on a shape mismatch, so this should never fire — but a card
 * that throws for any other reason must not take the whole transcript down
 * mid-demo. React 19 still has no hook form of an error boundary, so this is a
 * class component.
 */
export class CardErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
```

- [ ] **Step 5: `cards/fallback-card.tsx`**

```tsx
"use client";

import { useState } from "react";

import { ChatCard } from "./chat-card";
import { parseToolOutput } from "./parse-tool-output";

/**
 * Whatever a tool returned, shown safely. Used for any tool with no registered
 * card, and as the shape-mismatch fallback inside every typed card. Top-level
 * scalar fields are listed as key/value; the full payload is behind a toggle.
 */
export function FallbackCard({ output }: { output: unknown }) {
  const [open, setOpen] = useState(false);
  const parsed = parseToolOutput(output);
  const entries =
    parsed != null && typeof parsed === "object" && !Array.isArray(parsed)
      ? Object.entries(parsed as Record<string, unknown>).filter(
          ([, v]) => v == null || typeof v !== "object",
        )
      : [];

  return (
    <ChatCard title="Result">
      {entries.length > 0 && (
        <dl className="grid grid-cols-2 gap-x-2 gap-y-1" data-numeric>
          {entries.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="text-muted-foreground">{key}</dt>
              <dd>{String(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="self-start text-xs text-primary hover:underline"
      >
        {open ? "Hide raw data" : "Show raw data"}
      </button>
      {open && (
        <pre className="overflow-x-auto rounded-(--radius) bg-muted p-2 font-mono text-xs">
          {JSON.stringify(parsed, null, 2)}
        </pre>
      )}
    </ChatCard>
  );
}
```

- [ ] **Step 6: `cards/registry.tsx`**

```tsx
"use client";

import type { ToolUIPart } from "../use-panel-state";
import { CardErrorBoundary } from "./card-error-boundary";
import { FallbackCard } from "./fallback-card";

/**
 * The one place a tool name maps to a card. Every entry is keyed by the wire
 * part type — "tool-<mcp_tool_name>" — so a new backend tool renders through
 * <FallbackCard> until someone deliberately adds a row here. No tool name is
 * hardcoded anywhere else (Global Constraint, see use-panel-state.ts).
 *
 * Populated by the card tasks that follow. Empty here on purpose.
 */
export type ToolCard = (props: { output: unknown }) => React.ReactNode;

export const CARD_REGISTRY: Record<string, ToolCard> = {};

/**
 * Render the card for one `output-available` tool part. Read tools have no
 * `approval` object; parts that do (the write-side tools) are handled by the
 * panel's separate approval/success treatment and must not be passed here.
 */
export function renderToolCard(part: ToolUIPart): React.ReactNode {
  const Card = CARD_REGISTRY[part.type] ?? FallbackCard;
  return (
    <CardErrorBoundary fallback={<FallbackCard output={part.output} />}>
      <Card output={part.output} />
    </CardErrorBoundary>
  );
}
```

- [ ] **Step 7: Rewire `message-list.tsx`**

Replace the whole file with:

```tsx
"use client";

import type { UIMessage } from "@ai-sdk/react";

import { Markdown } from "./markdown";
import type { ToolUIPart } from "./use-panel-state";
import { renderToolCard } from "./cards/registry";

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
        const isLast = index === messages.length - 1;

        if (message.role === "user") {
          const text = textOf(message);
          if (!text) return null;
          return (
            <div
              key={message.id}
              className="self-end rounded-(--radius) bg-primary px-3 py-2 text-sm text-primary-foreground"
            >
              {text}
            </div>
          );
        }

        // Assistant: render each part in document order — text parts as Markdown
        // bubbles, read-tool outputs as cards. A turn can carry several tool
        // parts and several text parts (spec finding 8); order is preserved.
        const lastTextPartIndex = message.parts.reduce(
          (acc, part, i) => (part.type === "text" ? i : acc),
          -1,
        );

        const rendered = message.parts
          .map((part, i) => {
            if (part.type === "text") {
              const text = (part as { text: string }).text;
              if (!text) return null;
              const streamingHere = isLast && isStreaming && i === lastTextPartIndex;
              return (
                <div
                  key={`t${i}`}
                  className="self-start rounded-(--radius) bg-secondary px-3 py-2 text-sm text-secondary-foreground"
                >
                  <Markdown isAnimating={streamingHere}>{text}</Markdown>
                </div>
              );
            }

            if (part.type.startsWith("tool-")) {
              const toolPart = part as unknown as ToolUIPart;
              // Read tools only. A part with an `approval` object is a
              // write-side tool rendered by the panel's approval/success cards.
              if (toolPart.state === "output-available" && !toolPart.approval) {
                return <div key={`c${i}`}>{renderToolCard(toolPart)}</div>;
              }
            }

            return null;
          })
          .filter((node) => node !== null);

        if (rendered.length === 0) return null;

        return (
          <div key={message.id} className="flex flex-col items-stretch gap-stack">
            {rendered}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 8: Wrap the panel body in the mode provider — `agent-panel.tsx`**

Add the import:

```tsx
import { ChatModeProvider } from "./agent-panel/chat-mode-context";
```

In `ConnectedAgentPanel`, wrap the returned `<aside>...</aside>` so `mode` reaches the cards:

```tsx
  return (
    <ChatModeProvider mode={mode}>
      <aside
        className={cn(
          "flex h-full min-h-0 flex-col gap-stack border-border bg-card p-section",
          mode === "expanded" ? "min-w-0 flex-1" : "w-64 shrink-0 border-l",
        )}
      >
        {/* ...unchanged body... */}
      </aside>
    </ChatModeProvider>
  );
```

Do **not** touch the `state === "approval"` / `state === "success"` blocks or `classifyPanelState` — those keep working exactly as they do now.

- [ ] **Step 9: Type-check and lint**

Run from `frontend/`:

```bash
npx tsc --noEmit
npm run lint
```

Expected: both exit 0. If `tsc` complains that `React` is not in scope in `registry.tsx` / `card-error-boundary.tsx`, add `import type * as React from "react";` (or use `ReactNode` from `"react"` as the return type) — match whatever the existing card files do (`success-card.tsx` returns JSX with no explicit React import, so the automatic JSX runtime is on; `React.ReactNode` in a type position needs the import).

- [ ] **Step 10: Manual smoke check (optional but recommended)**

If the dev server is up (`npm run dev` in `frontend/`, `uvicorn`/agent running) and you are signed in as `amzal` / `12345`: ask the chat "list all products". Expected: below the reply you now see a **Result** card (the `FallbackCard`) with a "Show raw data" toggle. Text still renders as Markdown. Approval flow (ask it to "add 5 units to <some sku>") still shows the confirm/cancel card. If the dev server is wedged (not hydrating), skip — the walkthrough task covers this.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/components/shell/agent-panel/chat-mode-context.tsx \
        frontend/src/components/shell/agent-panel/cards/ \
        frontend/src/components/shell/agent-panel/message-list.tsx \
        frontend/src/components/shell/agent-panel.tsx
git commit -m "feat(chat): card registry + fallback card + inline tool-output rendering (gate 34)"
```

---

### Task 2: Prompt line — tell the model not to re-type list rows

**Files:**
- Modify: `agent/conversation.py` (the `INSTRUCTIONS` constant, currently ends `"...rather than silently accepting the default and asking afterward."`)
- Test: `agent/tests/test_instructions.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing importable. `INSTRUCTIONS` stays a module-level `str`.

**Backend TDD applies here.** Run agent tests from `agent/` with the agent venv active (`agent/tests/` uses no database — see its conftest).

- [ ] **Step 1: Write the failing test — `agent/tests/test_instructions.py`**

```python
"""Gate 34: the agent is told not to re-type tool list rows the UI already shows."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conversation import INSTRUCTIONS  # noqa: E402


def test_instructions_tell_the_model_not_to_retype_list_rows():
    lowered = INSTRUCTIONS.lower()
    assert "re-type" in lowered or "retype" in lowered or "repeat every" in lowered
    # The point of the line: a one-sentence summary is enough because the
    # interface renders the detail.
    assert "summar" in lowered
```

- [ ] **Step 2: Run it, watch it fail**

```bash
cd agent && python -m pytest tests/test_instructions.py -v
```

Expected: FAIL — `assert "re-type" in lowered ...` is False; the current `INSTRUCTIONS` says nothing about lists.

- [ ] **Step 3: Append the sentence in `agent/conversation.py`**

The `INSTRUCTIONS` string is a parenthesised implicit concatenation ending with:

```python
    "given them, rather than silently accepting the default and asking "
    "afterward."
```

Change the final fragment to add one sentence:

```python
    "given them, rather than silently accepting the default and asking "
    "afterward. When a tool returns a list of rows, give a one-sentence "
    "summary of what it found and do not re-type the individual rows - the "
    "interface renders them as a table for the user already."
```

Nothing else in the file changes. No new import, no signature change.

- [ ] **Step 4: Run the test, watch it pass; run the whole agent suite**

```bash
cd agent && python -m pytest tests/test_instructions.py -v
cd agent && python -m pytest -q
```

Expected: `test_instructions.py` passes; the full suite (~40 tests) still passes. If a test asserts on `INSTRUCTIONS` verbatim (grep `tests/` for `INSTRUCTIONS` first — none is expected), update its expected string to match.

- [ ] **Step 5: Commit**

```bash
git add agent/conversation.py agent/tests/test_instructions.py
git commit -m "feat(agent): instruct the model not to re-type tool list rows (gate 34)"
```

---

### Task 3: `ChatCardTable` — responsive table / stacked blocks

**Files:**
- Create: `frontend/src/components/shell/agent-panel/cards/chat-card-table.tsx`

**Interfaces:**
- Consumes: `useChatMode` from `../chat-mode-context`; `cn` from `@/lib/utils`; `Link` from `next/link`.
- Produces:

  ```typescript
  export type ChatCardColumn<Row> = {
    key: string;
    header: string;
    cell: (row: Row) => React.ReactNode;
    numeric?: boolean; // right-align + tabular-nums
  };

  export function ChatCardTable<Row>(props: {
    columns: ChatCardColumn<Row>[];
    rows: Row[];
    rowKey: (row: Row, index: number) => string;
    cap?: number;                       // default 5; rows beyond are hidden
    overflow?: { href: string; label: (hiddenCount: number) => string };
  }): React.ReactNode;
  ```

**Ruling (recorded here, not asked):** the spec's phrasing preferred "CSS block-display degradation, not a second render path"; this task branches on `useChatMode()` inside the one component instead. Reason: a container-query `::before`/`data-label` responsive-table trick is fiddly to get right and this is a time-boxed gate. It is still one component in one file that owns both layouts — the maintenance property the spec wanted. Cost if wrong: a later reader expecting pure CSS finds a JS branch; trivial.

- [ ] **Step 1: Write `chat-card-table.tsx`**

```tsx
"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { useChatMode } from "../chat-mode-context";
import { cn } from "@/lib/utils";

export type ChatCardColumn<Row> = {
  key: string;
  header: string;
  cell: (row: Row) => ReactNode;
  numeric?: boolean;
};

/**
 * A dense read-only table for a response card. Expanded panel: a real table
 * with a header row. Docked panel (256px rail): each row becomes a stacked
 * label/value block, because a five-column table does not fit 256px. One
 * component, both layouts — cards never think about panel width.
 *
 * `cap` caps the visible rows; `overflow` renders a "view all" link when rows
 * were hidden. tabular-nums comes from the `data-numeric` attribute (see
 * globals.css) plus per-column `numeric`.
 */
export function ChatCardTable<Row>({
  columns,
  rows,
  rowKey,
  cap = 5,
  overflow,
}: {
  columns: ChatCardColumn<Row>[];
  rows: Row[];
  rowKey: (row: Row, index: number) => string;
  cap?: number;
  overflow?: { href: string; label: (hiddenCount: number) => string };
}) {
  const mode = useChatMode();
  const shown = rows.slice(0, cap);
  const hidden = rows.length - shown.length;

  const overflowLink =
    overflow && hidden > 0 ? (
      <Link href={overflow.href} className="text-xs text-primary hover:underline">
        {overflow.label(hidden)}
      </Link>
    ) : null;

  if (mode === "docked") {
    return (
      <div className="flex flex-col gap-2">
        {shown.map((row, i) => (
          <div
            key={rowKey(row, i)}
            className="flex flex-col gap-0.5 rounded-(--radius) border border-border p-2"
            data-numeric
          >
            {columns.map((col) => (
              <div key={col.key} className="flex justify-between gap-2">
                <span className="text-muted-foreground">{col.header}</span>
                <span className={cn(col.numeric && "tabular-nums")}>{col.cell(row)}</span>
              </div>
            ))}
          </div>
        ))}
        {overflowLink}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-numeric>
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cn("py-1 pr-3 font-medium", col.numeric && "text-right pr-0")}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, i) => (
              <tr key={rowKey(row, i)} className="border-b border-border last:border-0">
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={cn(
                      "py-1 pr-3 align-top",
                      col.numeric && "text-right pr-0 tabular-nums",
                    )}
                  >
                    {col.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {overflowLink}
    </div>
  );
}
```

- [ ] **Step 2: Type-check and lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: exit 0. (`ChatCardTable` has no consumer yet — that is fine; `tsc` still checks it.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/shell/agent-panel/cards/chat-card-table.tsx
git commit -m "feat(chat): responsive ChatCardTable for response cards (gate 34)"
```

---

### Task 4: Product cards — `ProductListCard`, `ProductCard`

**Files:**
- Create: `frontend/src/components/shell/agent-panel/cards/product-cards.tsx`
- Modify: `frontend/src/components/shell/agent-panel/cards/registry.tsx` (add two entries)
- Modify: `frontend/src/components/shell/agent-panel/cards/fixtures.ts` (create + two fixtures) — create the file in this task

**Interfaces:**
- Consumes: `ProductOut`, `ProductListOut` from `@/lib/api/mcp-types`; `parseToolOutput` from `./parse-tool-output`; `ChatCard` from `./chat-card`; `ChatCardTable` + `ChatCardColumn` from `./chat-card-table`; `FallbackCard` from `./fallback-card`; `formatMoney` from `@/lib/format`; `StockBadge` from `@/components/domain/stock-badge`; `Link` from `next/link`.
- Produces: `ProductListCard`, `ProductCard` (both `ToolCard`); registry rows `"tool-list_products"`, `"tool-get_product"`, `"tool-get_product_by_sku"`.

**Note on `MCPToolOutputs` import path:** `frontend/src/lib/api/mcp-types.d.ts` declares the interfaces at module scope. Import as `import type { ProductOut, ProductListOut } from "@/lib/api/mcp-types";`. Confirm the path resolves (`tsc` will tell you); the file is at `frontend/src/lib/api/mcp-types.d.ts` so `@/lib/api/mcp-types` is correct.

- [ ] **Step 1: Write `product-cards.tsx`**

```tsx
"use client";

import Link from "next/link";

import type { ProductListOut, ProductOut } from "@/lib/api/mcp-types";
import { ChatCard } from "./chat-card";
import { ChatCardTable, type ChatCardColumn } from "./chat-card-table";
import { FallbackCard } from "./fallback-card";
import { parseToolOutput } from "./parse-tool-output";
import { formatMoney } from "@/lib/format";
import { StockBadge } from "@/components/domain/stock-badge";

function isProductOut(v: unknown): v is ProductOut {
  return (
    v != null &&
    typeof v === "object" &&
    typeof (v as ProductOut).sku === "string" &&
    typeof (v as ProductOut).name === "string" &&
    typeof (v as ProductOut).sell_price === "string" &&
    typeof (v as ProductOut).quantity_on_hand === "number"
  );
}

function isProductListOut(v: unknown): v is ProductListOut {
  return (
    v != null &&
    typeof v === "object" &&
    Array.isArray((v as ProductListOut).products) &&
    typeof (v as ProductListOut).total === "number" &&
    (v as ProductListOut).products.every(isProductOut)
  );
}

const PRODUCT_COLUMNS: ChatCardColumn<ProductOut>[] = [
  { key: "sku", header: "SKU", cell: (p) => <span className="font-mono text-xs">{p.sku}</span> },
  { key: "name", header: "Name", cell: (p) => p.name },
  { key: "qty", header: "On hand", numeric: true, cell: (p) => p.quantity_on_hand },
  {
    key: "status",
    header: "Status",
    cell: (p) => (
      <StockBadge quantity_on_hand={p.quantity_on_hand} needs_reorder={p.needs_reorder} />
    ),
  },
  { key: "price", header: "Sell price", numeric: true, cell: (p) => formatMoney(p.sell_price) },
];

export function ProductListCard({ output }: { output: unknown }) {
  const data = parseToolOutput(output);
  if (!isProductListOut(data)) return <FallbackCard output={output} />;

  return (
    <ChatCard title="Products" headerRight={`${data.total} total`}>
      <ChatCardTable
        columns={PRODUCT_COLUMNS}
        rows={data.products}
        rowKey={(p) => p.sku}
        cap={5}
        overflow={{
          href: "/products",
          label: (n) => `View all ${data.total} in Products →`,
        }}
      />
    </ChatCard>
  );
}

export function ProductCard({ output }: { output: unknown }) {
  const p = parseToolOutput(output);
  if (!isProductOut(p)) return <FallbackCard output={output} />;

  const rows: [string, React.ReactNode][] = [
    ["SKU", <span className="font-mono text-xs">{p.sku}</span>],
    ["Category", p.category ?? "—"],
    ["Unit", p.unit],
    ["On hand", <span className="tabular-nums">{p.quantity_on_hand}</span>],
    ["Reorder level", <span className="tabular-nums">{p.reorder_level}</span>],
    ["Cost price", <span className="tabular-nums">{formatMoney(p.cost_price)}</span>],
    ["Sell price", <span className="tabular-nums">{formatMoney(p.sell_price)}</span>],
  ];

  return (
    <ChatCard
      title={p.name}
      headerRight={
        <StockBadge quantity_on_hand={p.quantity_on_hand} needs_reorder={p.needs_reorder} />
      }
    >
      <dl className="grid grid-cols-2 gap-x-2 gap-y-1" data-numeric>
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <Link
        href={`/products/${p.id}`}
        className="self-start text-xs text-primary hover:underline"
      >
        Open in Products →
      </Link>
    </ChatCard>
  );
}
```

- [ ] **Step 2: Register both — edit `registry.tsx`**

Change the import block and the map:

```tsx
import { ProductCard, ProductListCard } from "./product-cards";

export const CARD_REGISTRY: Record<string, ToolCard> = {
  "tool-list_products": ProductListCard,
  "tool-get_product": ProductCard,
  "tool-get_product_by_sku": ProductCard,
};
```

- [ ] **Step 3: Create `cards/fixtures.ts` with the two product fixtures**

```ts
/**
 * Typed sample payloads, one per registered card. Nothing imports these at
 * runtime — `tsc --noEmit` type-checks them against the generated
 * MCPToolOutputs contract, which is the shape guarantee this repo has instead
 * of a card test runner. They are also paste-ready for eyeballing a card
 * during the browser walkthrough.
 */
import type { MCPToolOutputs } from "@/lib/api/mcp-types";

export const listProductsFixture: MCPToolOutputs["list_products"] = {
  total: 2,
  products: [
    {
      id: 1,
      sku: "2002-1001",
      name: "Full Cream Milk 1L",
      category: "Dairy",
      unit: "bottle",
      cost_price: "380.00",
      sell_price: "420.50",
      quantity_on_hand: 48,
      reorder_level: 24,
      needs_reorder: false,
      updated_by: "api",
    },
    {
      id: 2,
      sku: "2002-1002",
      name: "Sparkling Water 1.5L",
      category: "Beverages",
      unit: "bottle",
      cost_price: "150.00",
      sell_price: "190.00",
      quantity_on_hand: 0,
      reorder_level: 24,
      needs_reorder: true,
      updated_by: "mcp",
    },
  ],
};

export const getProductFixture: MCPToolOutputs["get_product"] = listProductsFixture.products[0];
```

- [ ] **Step 4: Type-check and lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: exit 0. A `tsc` error in `fixtures.ts` means the fixture does not match the generated schema — fix the fixture, not the schema. If `tsc` flags the inline `React.ReactNode` tuple type in `ProductCard`, add `import type { ReactNode } from "react";` and use `[string, ReactNode][]`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shell/agent-panel/cards/product-cards.tsx \
        frontend/src/components/shell/agent-panel/cards/registry.tsx \
        frontend/src/components/shell/agent-panel/cards/fixtures.ts
git commit -m "feat(chat): ProductListCard + ProductCard (gate 34)"
```

---

### Task 5: Inventory cards — `SpoilageCard`, `LotsCard`

**Files:**
- Create: `frontend/src/components/shell/agent-panel/cards/inventory-cards.tsx`
- Modify: `frontend/src/components/shell/agent-panel/cards/registry.tsx` (add two entries)
- Modify: `frontend/src/components/shell/agent-panel/cards/fixtures.ts` (add two fixtures)

**Interfaces:**
- Consumes: `SpoilageReportOut`, `SpoilageItemOut`, `LotListOut`, `LotOut`, `MCPToolOutputs` from `@/lib/api/mcp-types`; `ChatCard`, `ChatCardTable` + `ChatCardColumn`, `FallbackCard`, `parseToolOutput`; `formatMoney`, `formatDate`, `formatDaysRemaining` from `@/lib/format`.
- Produces: `SpoilageCard`, `LotsCard`; registry rows `"tool-check_spoilage_risk"`, `"tool-list_product_lots"`.

**Date fields:** `check_spoilage_risk.scanned_on` and `list_product_lots.lots[].expiry_date` are calendar dates (`"2026-08-29"`) — use `formatDate`. `days_remaining` is an integer — use `formatDaysRemaining`. If a live payload during the walkthrough shows `scanned_on` as a timestamp, switch that one field to `formatDateTime`; both are pure string formatters and the wrong choice is cosmetic.

- [ ] **Step 1: Write `inventory-cards.tsx`**

```tsx
"use client";

import Link from "next/link";

import type {
  LotListOut,
  LotOut,
  SpoilageItemOut,
  SpoilageReportOut,
} from "@/lib/api/mcp-types";
import { ChatCard } from "./chat-card";
import { ChatCardTable, type ChatCardColumn } from "./chat-card-table";
import { FallbackCard } from "./fallback-card";
import { parseToolOutput } from "./parse-tool-output";
import { formatDate, formatDaysRemaining, formatMoney } from "@/lib/format";

function isSpoilageReportOut(v: unknown): v is SpoilageReportOut {
  return (
    v != null &&
    typeof v === "object" &&
    Array.isArray((v as SpoilageReportOut).items) &&
    typeof (v as SpoilageReportOut).total_cost_at_risk === "string" &&
    typeof (v as SpoilageReportOut).scanned_on === "string"
  );
}

function isLotListOut(v: unknown): v is LotListOut {
  return (
    v != null &&
    typeof v === "object" &&
    Array.isArray((v as LotListOut).lots) &&
    (v as LotListOut).lots.every(
      (l) => l != null && typeof (l as LotOut).lot_code === "string",
    )
  );
}

const SPOILAGE_COLUMNS: ChatCardColumn<SpoilageItemOut>[] = [
  { key: "product", header: "Product", cell: (i) => i.product_name },
  { key: "lot", header: "Lot", cell: (i) => <span className="font-mono text-xs">{i.lot_code}</span> },
  { key: "expiry", header: "Expires", cell: (i) => formatDaysRemaining(i.days_remaining) },
  { key: "qty", header: "Qty", numeric: true, cell: (i) => i.quantity },
  {
    key: "price",
    header: "Now → markdown",
    numeric: true,
    cell: (i) => `${formatMoney(i.current_price)} → ${formatMoney(i.proposed_price)}`,
  },
  {
    key: "risk",
    header: "At risk",
    numeric: true,
    cell: (i) => formatMoney(i.cost_at_risk),
  },
];

export function SpoilageCard({ output }: { output: unknown }) {
  const data = parseToolOutput(output);
  if (!isSpoilageReportOut(data)) return <FallbackCard output={output} />;

  return (
    <ChatCard
      title="Spoilage risk"
      headerRight={`scanned ${formatDate(data.scanned_on)} · ${data.within_days}d window`}
    >
      {data.items.length === 0 ? (
        <p className="text-muted-foreground">Nothing at risk in the next {data.within_days} days.</p>
      ) : (
        <>
          <ChatCardTable
            columns={SPOILAGE_COLUMNS}
            rows={data.items}
            rowKey={(i) => String(i.lot_id)}
            cap={6}
            overflow={{
              href: "/inventory/spoilage",
              label: () => "Open spoilage review →",
            }}
          />
          <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
            <span>Total at risk: {formatMoney(data.total_cost_at_risk)}</span>
            <span>Recoverable: {formatMoney(data.total_projected_recovery)}</span>
          </div>
        </>
      )}
    </ChatCard>
  );
}

const LOT_COLUMNS: ChatCardColumn<LotOut>[] = [
  { key: "code", header: "Lot", cell: (l) => <span className="font-mono text-xs">{l.lot_code}</span> },
  {
    key: "expiry",
    header: "Expiry",
    cell: (l) =>
      l.expiry_date ? formatDate(l.expiry_date) : <span className="text-muted-foreground">—</span>,
  },
  { key: "qty", header: "Qty", numeric: true, cell: (l) => l.quantity },
  { key: "cost", header: "Cost", numeric: true, cell: (l) => formatMoney(l.cost_price) },
];

export function LotsCard({ output }: { output: unknown }) {
  const data = parseToolOutput(output);
  if (!isLotListOut(data)) return <FallbackCard output={output} />;

  // Soonest expiry first; nulls (no expiry) last.
  const lots = [...data.lots].sort((a, b) => {
    if (!a.expiry_date) return 1;
    if (!b.expiry_date) return -1;
    return a.expiry_date.localeCompare(b.expiry_date);
  });

  return (
    <ChatCard title="Stock lots" headerRight={`${data.lots.length} ${data.lots.length === 1 ? "lot" : "lots"}`}>
      {lots.length === 0 ? (
        <p className="text-muted-foreground">No lots on record.</p>
      ) : (
        <ChatCardTable
          columns={LOT_COLUMNS}
          rows={lots}
          rowKey={(l) => String(l.lot_id)}
          cap={6}
          overflow={
            lots[0]
              ? { href: `/products/${lots[0].product_id}`, label: () => "Open product →" }
              : undefined
          }
        />
      )}
    </ChatCard>
  );
}
```

- [ ] **Step 2: Register — edit `registry.tsx`**

```tsx
import { LotsCard, SpoilageCard } from "./inventory-cards";

// ...in CARD_REGISTRY:
  "tool-check_spoilage_risk": SpoilageCard,
  "tool-list_product_lots": LotsCard,
```

- [ ] **Step 3: Add fixtures to `fixtures.ts`**

```ts
export const checkSpoilageRiskFixture: MCPToolOutputs["check_spoilage_risk"] = {
  scanned_on: "2026-09-10",
  within_days: 7,
  total_cost_at_risk: "4560.00",
  total_projected_recovery: "2280.00",
  items: [
    {
      lot_id: 12,
      product_id: 1,
      sku: "2002-1001",
      product_name: "Full Cream Milk 1L",
      lot_code: "L-2609-A",
      expiry_date: "2026-09-14",
      days_remaining: 4,
      quantity: 18,
      current_price: "420.50",
      proposed_price: "294.35",
      discount_percent: 30,
      why: "Expires within the markdown window",
      cost_at_risk: "6840.00",
      projected_recovery: "5298.30",
    },
  ],
};

export const listProductLotsFixture: MCPToolOutputs["list_product_lots"] = {
  lots: [
    {
      lot_id: 12,
      product_id: 1,
      lot_code: "L-2609-A",
      expiry_date: "2026-09-14",
      quantity: 18,
      cost_price: "380.00",
      sell_price: "420.50",
      discount_percent: 0,
      is_expired: false,
    },
    {
      lot_id: 9,
      product_id: 1,
      lot_code: "L-2608-B",
      expiry_date: null,
      quantity: 6,
      cost_price: "375.00",
      sell_price: "420.50",
      discount_percent: 0,
      is_expired: false,
    },
  ],
};
```

- [ ] **Step 4: Type-check and lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shell/agent-panel/cards/inventory-cards.tsx \
        frontend/src/components/shell/agent-panel/cards/registry.tsx \
        frontend/src/components/shell/agent-panel/cards/fixtures.ts
git commit -m "feat(chat): SpoilageCard + LotsCard (gate 34)"
```

---

### Task 6: Purchasing cards — `ReorderBundlesCard`, `PendingDraftsCard`, `PurchaseOrdersCard`

**Files:**
- Create: `frontend/src/components/shell/agent-panel/cards/purchasing-cards.tsx`
- Modify: `frontend/src/components/shell/agent-panel/cards/registry.tsx` (add three entries)
- Modify: `frontend/src/components/shell/agent-panel/cards/fixtures.ts` (add three fixtures)

**Interfaces:**
- Consumes: `ReorderReportOut`, `ReorderBundleOut`, `ReorderLineOut`, `DraftListOut`, `DraftOut`, `PurchaseOrderListOut`, `PurchaseOrderOut`, `MCPToolOutputs` from `@/lib/api/mcp-types`; the shared card parts; `formatMoney`, `formatDate` from `@/lib/format`.
- Produces: `ReorderBundlesCard`, `PendingDraftsCard`, `PurchaseOrdersCard`; registry rows `"tool-suggest_reorder_bundles"`, `"tool-list_pending_drafts"`, `"tool-list_purchase_orders"`.

**`DraftOut.payload` is `{ [k: string]: unknown }`** (polymorphic by `draft_type`, spec finding 10). Do not add a type for it — read it defensively at runtime: `SUPPLIER_REORDER` → `{ supplier_id, expected_date, lines: [{product_id, quantity, unit_cost}] }`; `BATCH_PRICE_MARKDOWN` → `{ lines: [{lot_id, product_id, new_price}] }`. The card shows a one-line summary per draft, not the line items, so a missing/renamed payload field degrades to "N/A" text, never a crash.

**Line items carry `product_id` only, no name (spec finding 9).** These cards deliberately show summary counts and totals, not per-line product names — so no name resolution is needed. `ReorderLineOut` / `UnsourcedOut` *do* carry `name`/`sku`; use them directly there.

**Routes:** `/purchasing` (reorder), `/approvals` (drafts), `/purchasing/orders` (purchase orders) — all exist.

- [ ] **Step 1: Write `purchasing-cards.tsx`**

```tsx
"use client";

import Link from "next/link";

import type {
  DraftListOut,
  DraftOut,
  PurchaseOrderListOut,
  PurchaseOrderOut,
  ReorderBundleOut,
  ReorderLineOut,
  ReorderReportOut,
} from "@/lib/api/mcp-types";
import { ChatCard } from "./chat-card";
import { ChatCardTable, type ChatCardColumn } from "./chat-card-table";
import { FallbackCard } from "./fallback-card";
import { parseToolOutput } from "./parse-tool-output";
import { formatMoney } from "@/lib/format";

/* ---------- suggest_reorder_bundles ---------- */

function isReorderReportOut(v: unknown): v is ReorderReportOut {
  return (
    v != null &&
    typeof v === "object" &&
    Array.isArray((v as ReorderReportOut).bundles) &&
    Array.isArray((v as ReorderReportOut).unsourced) &&
    typeof (v as ReorderReportOut).total_value === "string"
  );
}

const BUNDLE_LINE_COLUMNS: ChatCardColumn<ReorderLineOut>[] = [
  { key: "name", header: "Product", cell: (l) => l.name },
  { key: "qty", header: "Order qty", numeric: true, cell: (l) => l.quantity },
  { key: "unit", header: "Unit cost", numeric: true, cell: (l) => formatMoney(l.unit_cost) },
  { key: "total", header: "Line total", numeric: true, cell: (l) => formatMoney(l.line_total) },
];

function BundleSection({ bundle }: { bundle: ReorderBundleOut }) {
  return (
    <div className="flex flex-col gap-1 rounded-(--radius) border border-border p-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-medium">{bundle.supplier_name}</span>
        <span className="text-xs text-muted-foreground tabular-nums">
          {formatMoney(bundle.bundle_value)}
          {bundle.below_minimum ? " · below minimum" : ""}
        </span>
      </div>
      <ChatCardTable
        columns={BUNDLE_LINE_COLUMNS}
        rows={bundle.lines}
        rowKey={(l) => String(l.product_id)}
        cap={4}
      />
    </div>
  );
}

export function ReorderBundlesCard({ output }: { output: unknown }) {
  const data = parseToolOutput(output);
  if (!isReorderReportOut(data)) return <FallbackCard output={output} />;

  return (
    <ChatCard title="Suggested reorder" headerRight={`${formatMoney(data.total_value)} total`}>
      {data.bundles.length === 0 ? (
        <p className="text-muted-foreground">Nothing needs reordering.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {data.bundles.map((b) => (
            <BundleSection key={b.supplier_id} bundle={b} />
          ))}
        </div>
      )}
      {data.unsourced.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {data.unsourced.length} item{data.unsourced.length === 1 ? "" : "s"} with no supplier:{" "}
          {data.unsourced.map((u) => u.name).join(", ")}
        </p>
      )}
      <Link href="/purchasing" className="self-start text-xs text-primary hover:underline">
        Open purchasing →
      </Link>
    </ChatCard>
  );
}

/* ---------- list_pending_drafts ---------- */

function isDraftListOut(v: unknown): v is DraftListOut {
  return (
    v != null &&
    typeof v === "object" &&
    Array.isArray((v as DraftListOut).drafts) &&
    (v as DraftListOut).drafts.every(
      (d) => d != null && typeof (d as DraftOut).draft_type === "string",
    )
  );
}

function draftSummary(draft: DraftOut): string {
  const payload = (draft.payload ?? {}) as Record<string, unknown>;
  const lines = Array.isArray(payload.lines) ? (payload.lines as unknown[]) : [];
  if (draft.draft_type === "SUPPLIER_REORDER") {
    const supplier = payload.supplier_id != null ? `supplier #${String(payload.supplier_id)}` : "a supplier";
    return `Reorder ${lines.length} item${lines.length === 1 ? "" : "s"} from ${supplier}`;
  }
  if (draft.draft_type === "BATCH_PRICE_MARKDOWN") {
    return `Mark down ${lines.length} lot${lines.length === 1 ? "" : "s"}`;
  }
  return draft.draft_type.replace(/_/g, " ").toLowerCase();
}

export function PendingDraftsCard({ output }: { output: unknown }) {
  const data = parseToolOutput(output);
  if (!isDraftListOut(data)) return <FallbackCard output={output} />;

  return (
    <ChatCard
      title="Pending approvals"
      headerRight={`${data.drafts.length} waiting`}
    >
      {data.drafts.length === 0 ? (
        <p className="text-muted-foreground">Nothing waiting for approval.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {data.drafts.map((d) => (
            <li
              key={d.id}
              className="flex flex-col gap-0.5 rounded-(--radius) border border-border p-2"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-medium">{draftSummary(d)}</span>
                <span className="text-xs text-muted-foreground">
                  {d.is_expired ? "expired" : d.status.toLowerCase()}
                </span>
              </div>
              {d.reasoning && (
                <span className="text-xs text-muted-foreground">{d.reasoning}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      <Link href="/approvals" className="self-start text-xs text-primary hover:underline">
        Open approvals →
      </Link>
    </ChatCard>
  );
}

/* ---------- list_purchase_orders ---------- */

function isPurchaseOrderListOut(v: unknown): v is PurchaseOrderListOut {
  return (
    v != null &&
    typeof v === "object" &&
    Array.isArray((v as PurchaseOrderListOut).orders) &&
    typeof (v as PurchaseOrderListOut).total === "number"
  );
}

const PO_COLUMNS: ChatCardColumn<PurchaseOrderOut>[] = [
  { key: "id", header: "PO", cell: (o) => <span className="font-mono text-xs">#{o.id}</span> },
  { key: "supplier", header: "Supplier", numeric: true, cell: (o) => `#${o.supplier_id}` },
  { key: "status", header: "Status", cell: (o) => o.status.toLowerCase() },
  { key: "lines", header: "Lines", numeric: true, cell: (o) => o.lines.length },
  { key: "total", header: "Value", numeric: true, cell: (o) => formatMoney(o.total_value) },
];

export function PurchaseOrdersCard({ output }: { output: unknown }) {
  const data = parseToolOutput(output);
  if (!isPurchaseOrderListOut(data)) return <FallbackCard output={output} />;

  return (
    <ChatCard title="Purchase orders" headerRight={`${data.total} total`}>
      {data.orders.length === 0 ? (
        <p className="text-muted-foreground">No purchase orders.</p>
      ) : (
        <ChatCardTable
          columns={PO_COLUMNS}
          rows={data.orders}
          rowKey={(o) => String(o.id)}
          cap={5}
          overflow={{ href: "/purchasing/orders", label: (n) => `View all ${data.total} orders →` }}
        />
      )}
    </ChatCard>
  );
}
```

- [ ] **Step 2: Register — edit `registry.tsx`**

```tsx
import {
  PendingDraftsCard,
  PurchaseOrdersCard,
  ReorderBundlesCard,
} from "./purchasing-cards";

// ...in CARD_REGISTRY:
  "tool-suggest_reorder_bundles": ReorderBundlesCard,
  "tool-list_pending_drafts": PendingDraftsCard,
  "tool-list_purchase_orders": PurchaseOrdersCard,
```

- [ ] **Step 3: Add fixtures to `fixtures.ts`**

```ts
export const suggestReorderBundlesFixture: MCPToolOutputs["suggest_reorder_bundles"] = {
  total_value: "18400.00",
  bundles: [
    {
      supplier_id: 3,
      supplier_name: "Highland Dairy Co.",
      lead_time_days: 2,
      minimum_order_value: "10000.00",
      bundle_value: "12600.00",
      below_minimum: false,
      shortfall: "0.00",
      lines: [
        {
          product_id: 1,
          sku: "2002-1001",
          name: "Full Cream Milk 1L",
          quantity_on_hand: 6,
          reorder_level: 24,
          quantity: 48,
          unit_cost: "262.50",
          pack_size: 12,
          line_total: "12600.00",
          is_top_up: false,
        },
      ],
    },
  ],
  unsourced: [
    {
      product_id: 7,
      sku: "3001-2002",
      name: "House Blend Coffee 250g",
      quantity_on_hand: 2,
      reorder_level: 10,
    },
  ],
};

export const listPendingDraftsFixture: MCPToolOutputs["list_pending_drafts"] = {
  drafts: [
    {
      id: 41,
      draft_type: "SUPPLIER_REORDER",
      status: "PENDING",
      payload: {
        supplier_id: 3,
        expected_date: "2026-09-15",
        lines: [{ product_id: 1, quantity: 48, unit_cost: "262.50" }],
      },
      reasoning: "Milk is below reorder level with a 2-day lead time.",
      cost_at_risk: null,
      projected_recovery: null,
      expires_at: "2026-09-12",
      is_expired: false,
      created_by: "01a02d8f-1111-2222-3333-444455556666",
      created_via: "agent",
      decided_by: null,
      decided_via: null,
    },
  ],
};

export const listPurchaseOrdersFixture: MCPToolOutputs["list_purchase_orders"] = {
  total: 1,
  orders: [
    {
      id: 12,
      supplier_id: 3,
      status: "PLACED",
      expected_date: "2026-09-15",
      total_value: "12600.00",
      notes: null,
      source_draft_id: 41,
      created_by: "01a02d8f-1111-2222-3333-444455556666",
      lines: [
        { product_id: 1, quantity_ordered: 48, unit_cost: "262.50", line_total: "12600.00" },
      ],
    },
  ],
};
```

- [ ] **Step 4: Type-check and lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: exit 0. If the `draftSummary` payload access trips `no-explicit-any` or similar, keep the `as Record<string, unknown>` casts shown — they are the deliberate "payload is polymorphic" boundary.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shell/agent-panel/cards/purchasing-cards.tsx \
        frontend/src/components/shell/agent-panel/cards/registry.tsx \
        frontend/src/components/shell/agent-panel/cards/fixtures.ts
git commit -m "feat(chat): ReorderBundlesCard + PendingDraftsCard + PurchaseOrdersCard (gate 34)"
```

---

### Task 7: Restyle `ToolCallCard` and `SuccessCard` onto `ChatCard`

**Files:**
- Modify: `frontend/src/components/shell/agent-panel/tool-call-card.tsx`
- Modify: `frontend/src/components/shell/agent-panel/success-card.tsx`

**Interfaces:**
- Consumes: `ChatCard` from `./cards/chat-card`.
- Produces: nothing new. `ToolCallCard` and `SuccessCard` keep their exact current props and behaviour.

**Behaviour must not change.** The approval round-trip (`onRespond`), the `product_id` → label resolution (`useProductLabel` stays in `tool-call-card.tsx` — it is **not** extracted in this gate), and `SuccessCard`'s `updated_by` line all work exactly as before. This task only swaps the outer `<div className="...border...bg-card...">` for `<ChatCard>`.

- [ ] **Step 1: `tool-call-card.tsx` — replace the outer wrapper**

The component currently returns:

```tsx
  return (
    <div className="flex flex-col gap-2 rounded-(--radius) border border-border bg-card p-3 text-sm">
      <div className="text-xs font-semibold uppercase text-muted-foreground">
        {actionLabel(part.type)}
      </div>
      <dl className="grid grid-cols-2 gap-x-2 gap-y-1" data-numeric>
        {/* ...unchanged... */}
      </dl>
      <div className="flex gap-2 pt-1">
        <Button type="button" onClick={() => onRespond(true)}>Confirm</Button>
        <Button type="button" variant="outline" onClick={() => onRespond(false)}>Cancel</Button>
      </div>
    </div>
  );
```

Change it to:

```tsx
  return (
    <ChatCard title={actionLabel(part.type)}>
      <dl className="grid grid-cols-2 gap-x-2 gap-y-1" data-numeric>
        {/* ...unchanged... */}
      </dl>
      <div className="flex gap-2 pt-1">
        <Button type="button" onClick={() => onRespond(true)}>Confirm</Button>
        <Button type="button" variant="outline" onClick={() => onRespond(false)}>Cancel</Button>
      </div>
    </ChatCard>
  );
```

Add `import { ChatCard } from "./cards/chat-card";` and delete the now-unused inline title `<div>`. Keep everything else — `actionLabel`, `useProductLabel`, the `<dl>` body — byte-for-byte.

- [ ] **Step 2: `success-card.tsx` — replace the outer wrapper**

Currently returns:

```tsx
  return (
    <div className="flex flex-col gap-1 rounded-(--radius) border border-border bg-card p-3 text-sm">
      <div>Done — {String(part.output ?? "the change was applied")}.</div>
      {sku && (
        <Link href={`/products?search=${encodeURIComponent(sku)}`} className="text-primary hover:underline">
          View product →
        </Link>
      )}
      {who && (
        <div className="font-mono text-xs text-muted-foreground">updated_by: {who}</div>
      )}
    </div>
  );
```

Change to:

```tsx
  return (
    <ChatCard title="Done">
      <div>{String(part.output ?? "the change was applied")}.</div>
      {sku && (
        <Link href={`/products?search=${encodeURIComponent(sku)}`} className="text-primary hover:underline">
          View product →
        </Link>
      )}
      {who && (
        <div className="font-mono text-xs text-muted-foreground">updated_by: {who}</div>
      )}
    </ChatCard>
  );
```

Add `import { ChatCard } from "./cards/chat-card";`. Keep `updatedBy`, the `sku` extraction, and the `Link` exactly as they are. (The visible "Done — " prefix moves into the card title; that is the one intentional copy change.)

- [ ] **Step 3: Type-check and lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/shell/agent-panel/tool-call-card.tsx \
        frontend/src/components/shell/agent-panel/success-card.tsx
git commit -m "feat(chat): re-parent approval + success cards onto ChatCard shell (gate 34)"
```

---

### Task 8: Browser walkthrough + docs

**Files:**
- Modify: `docs/PLAN.md` (gate 34 row → done, with commit range)
- Modify: `docs/FRONTEND-PLAN.md` (note the card registry + the no-runner verification approach)
- Modify: `docs/DEPLOY-PLAN.md` ("what a new feature has to update in the box" → gate 34 owes nothing)
- Modify: `docs/superpowers/specs/2026-09-09-chatbot-overhaul-design.md` (status line → gate 34 shipped; drop the "name resolution" paragraph's extraction claim — see below)

**This task has no code. It verifies the built feature and records completion.**

- [ ] **Step 1: Full type-check, lint, and agent suite at HEAD**

```bash
cd frontend && npx tsc --noEmit && npm run lint
cd ../agent && python -m pytest -q
```

Expected: all clean. Record the counts.

- [ ] **Step 2: Browser walkthrough**

Prerequisite: the developer has started `uvicorn` (backend :8000), the agent service (:8002), and `npm run dev` (frontend :3000), and confirmed the page hydrates (the gate-33 session hit a wedged dev server — if buttons are dead, ask the developer to restart `npm run dev` before continuing). Sign in as `amzal` / `12345`.

Use chrome-devtools MCP. For each prompt below: send it, wait for the reply, take a snapshot, confirm the described card renders, then toggle the panel to expanded (the maximise icon in the panel header) and confirm the table layout. Note anything that looks wrong; do not fix inline — collect findings.

| Prompt | Expect |
|---|---|
| `list all products` | `ProductListCard` — "PRODUCTS" title, "N total" on the right, ~5 rows, "View all N in Products →". Docked: stacked blocks. Expanded: table with SKU/Name/On hand/Status/Sell price. |
| `show me the milk product` (or a real SKU) | `ProductCard` — product name as title, `StockBadge` top-right, the key/value grid, "Open in Products →". |
| `what's at risk of spoiling?` | `SpoilageCard` — "SPOILAGE RISK", scan date + window, at-risk lots, totals row. |
| `show the lots for <that SKU>` | one `ProductCard` **and** one `LotsCard` in the same reply, in order (spec finding 8). Lots soonest-expiry-first. |
| `what should I reorder?` | `ReorderBundlesCard` — grouped by supplier, line tables, total, any unsourced items listed. |
| `what's pending approval?` | `PendingDraftsCard` — one block per draft, type summary + status + reasoning. |
| `list purchase orders` | `PurchaseOrdersCard` — PO/supplier/status/lines/value. |
| `add 5 units to <SKU>` | the **approval** card (`ToolCallCard`) on the `ChatCard` shell — Confirm/Cancel. Confirm it → the **success** card (`SuccessCard`) on the `ChatCard` shell, with the `updated_by` line. |

Also confirm: a plain question with no tool call still renders as a Markdown bubble; the model's reply text no longer re-lists every row (the prompt line — it may still slip on Flash-Lite, which is acceptable).

- [ ] **Step 3: Fix any walkthrough findings**

If a card is broken, fix it now (small diff), re-run `tsc`/`lint`, re-verify that card, and commit as `fix(chat): <what> (gate 34)`. If a finding is cosmetic and non-blocking, write it into `docs/FRONTEND-PLAN.md` as a known follow-up instead.

- [ ] **Step 4: Update the docs**

`docs/PLAN.md` — set the gate 34 row to done, dated today, with the commit range from `git log --oneline` (first card-infra commit .. last commit).

`docs/FRONTEND-PLAN.md` — add a short subsection: the agent panel now has a card registry at `frontend/src/components/shell/agent-panel/cards/` (`tool-<name>` → component; unregistered tools render `FallbackCard`); cards are verified by `tsc` (typed fixtures in `cards/fixtures.ts`) + the manual walkthrough, since the frontend still has no test runner; reload persistence of tool cards is gate 34b.

`docs/DEPLOY-PLAN.md` — under "What a new feature has to update in the box", add: "Gate 34 (response cards): nothing. Frontend-only, no new permission, setting, or migration."

`docs/superpowers/specs/2026-09-09-chatbot-overhaul-design.md` — change the top status line to note gate 34 shipped (commit range) with the browser walkthrough done; in the "Name resolution" paragraph of the Gate 34 section, replace the `useProductLabel` extraction sentence with: "No card resolves `product_id` → name in this gate — bundles/unsourced carry `name`/`sku`, spoilage carries `product_name`, and the PO / draft cards show summary counts rather than line items. `useProductLabel` stays inline in `tool-call-card.tsx`."

- [ ] **Step 5: Commit the docs**

```bash
git add docs/PLAN.md docs/FRONTEND-PLAN.md docs/DEPLOY-PLAN.md \
        docs/superpowers/specs/2026-09-09-chatbot-overhaul-design.md
git commit -m "docs: mark gate 34 (response cards) done"
```

---

## Self-Review

**1. Spec coverage:**

| Spec requirement (Gate 34 section) | Task |
|---|---|
| Card registry `cards/`, `tool-<name>` → component | Task 1 (`registry.tsx`) + card tasks 4–6 |
| `MessageList` iterates every part in order; render read-tool cards; drop `if(!text)return null` | Task 1 (Step 7) |
| `ChatCard` shell + `ChatCardTable` | Tasks 1 + 3 |
| `FallbackCard` | Task 1 |
| 7 read cards (`ProductListCard`, `ProductCard`, `SpoilageCard`, `LotsCard`, `ReorderBundlesCard`, `PendingDraftsCard`, `PurchaseOrdersCard`) | Tasks 4, 5, 6 |
| Restyle `ToolCallCard` + `SuccessCard` onto `ChatCard` | Task 7 |
| One `INSTRUCTIONS` line in `agent/conversation.py` | Task 2 |
| `parseToolOutput` (object-or-string, never throws) | Task 1 |
| Type guard per card → `FallbackCard` on mismatch | Tasks 4–6 (each `is…` guard) |
| `ChatModeContext` for docked/expanded, provided in `AgentPanel` | Task 1 (Steps 1, 8) |
| Docked = degraded layout, expanded = table | Task 3 (branch on `useChatMode`) — **deviation from "CSS only", ruled in Task 3** |
| No tool name hardcoded outside the registry | Task 1 (`registry.tsx` is the only place) |
| Typed fixture per card | Tasks 4–6 (`cards/fixtures.ts`) |
| `tsc` + `lint` clean; browser walkthrough | every task + Task 8 |
| Owes the box nothing → `DEPLOY-PLAN.md` | Task 8 |
| Name resolution: line-item cards use a shared `useProductLabel` | **Dropped** — no card needs it (ruled in Task 6, spec updated in Task 8). |
| Reload persistence, R3, R4 | **Out of scope — gate 34b.** Not in this plan. |

**2. Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N". Every code step has the actual code. The date-formatter choice in Task 5 is specified per field with a fallback instruction, not left open.

**3. Type consistency:**
- `ToolCard` type: defined in `registry.tsx` (Task 1), used by all card tasks. The card component signature `({ output }: { output: unknown }) => React.ReactNode` matches `ToolCard` — consistent across Tasks 1, 4, 5, 6.
- `ChatCardColumn<Row>` / `ChatCardTable` props: defined in Task 3, consumed with the exact `{ columns, rows, rowKey, cap, overflow }` shape in Tasks 4, 5, 6.
- `ChatCard` props `{ title, headerRight?, children }`: defined Task 1, used Tasks 1, 4, 5, 6, 7.
- `useChatMode(): ChatMode` / `ChatModeProvider`: defined Task 1, consumed Task 3.
- `parseToolOutput`: defined Task 1, consumed Tasks 1 (FallbackCard), 4, 5, 6.
- Registry keys are the wire `part.type` (`"tool-" + mcp_tool_name`) — matches `MessageList`'s `part.type.startsWith("tool-")` check and the spec's captured wire format.
- `MCPToolOutputs` / individual `*Out` interface names match `frontend/src/lib/api/mcp-types.d.ts` exactly (verified against the generated file: `ProductOut`, `ProductListOut`, `SpoilageReportOut`, `SpoilageItemOut`, `LotOut`, `LotListOut`, `ReorderReportOut`, `ReorderBundleOut`, `ReorderLineOut`, `DraftOut`, `DraftListOut`, `PurchaseOrderOut`, `PurchaseOrderListOut`).

One gap found and fixed inline: Task 1's `registry.tsx` originally referenced card components before they existed. Resolved by shipping the registry **empty** in Task 1 (every output → `FallbackCard`) and having each card task add its own rows — so Task 1 compiles on its own and the infra is independently testable, matching the infra-first ordering the spec calls for.
