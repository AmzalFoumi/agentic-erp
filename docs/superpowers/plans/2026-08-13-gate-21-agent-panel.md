# Gate 21 — Frontend Agent Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `frontend/src/components/shell/agent-panel.tsx` to the agent's HTTP service (shipped Gate 20) via `@ai-sdk/react`'s `useChat`, replacing the static "unavailable" shell with the six designed states: idle, thinking, streaming reply, tool-call-in-progress (Confirm/Cancel), success, refusal.

**Architecture:** `agent-panel.tsx` becomes a thin shell that creates/loads a conversation and owns `useChat`; it renders one of six new leaf components under `agent-panel/` based on `useChat`'s own status and the current message's parts. All approval semantics (Confirm/Cancel → `DeferredToolRequests`) are handled by `@ai-sdk/react` v4's native `addToolApprovalResponse` — no hand-rolled protocol parsing.

**Tech Stack:** Next.js 16 (App Router, Client Component), `ai@7.0.64`, `@ai-sdk/react@4.0.67`, existing Tailwind v4 token system in `globals.css`.

## Global Constraints

- Version floor: `ai@7.0.64`, `@ai-sdk/react@4.0.67` — re-verified live on npm 2026-08-13, matches `agent/app.py`'s `SDK_VERSION = 7`. Below `@ai-sdk/react@4` (AI SDK v6 wire), approval parts don't exist.
- No new `fetch` calls and no new files under `src/app/api` — `frontend/eslint.config.mjs` enforces both as build errors. `useChat`'s transport must point at the existing proxy route `src/app/api/agent/[...path]/route.ts`.
- The proxy route is transport-only and already handles streaming passthrough (`frontend/src/app/api/agent/[...path]/route.ts`) — nothing in this plan touches it.
- No automated component tests in this gate (decided 2026-08-13: no test runner exists anywhere in `frontend/` yet; standing up Vitest/RTL/Playwright is its own separate plan). Verification is manual, in-browser, via chrome-devtools or playwright MCP, only after the developer confirms both `uvicorn` (backend, port 8000) and the agent service (`python -m agent.app` or equivalent, port 8002) and `npm run dev` are running.
- The developer runs every npm/git command. Every step that touches the toolchain is written as a handoff ("developer runs X, expects Y"), never executed by the agent. No agent-run `git commit`.
- Six states, not five — `docs/FRONTEND-PLAN.md` line 643-656 is authoritative; do not re-derive from `docs/AGENT-PLAN.md`'s prose, which is a pointer to the same table.
- Mutating tools (require approval): everything except `list_products`, `get_product`, `get_product_by_sku` (see `agent/mcp_client.py:84`, `READ_ONLY`). Do not hardcode a specific tool name like `adjust_stock` as the only mutating tool — the allowlist is inverted (reads are named, writes are everything else), and a new backend tool defaults to gated. Any UI copy that names a specific action must derive it from the tool name at render time, not assume there is only one mutating tool.
- Refusal has no distinct wire signal (confirmed this session: `part.state` values are `approval-requested` / `approval-responded` / `output-available` / `output-denied` — there is no `refused` state for plain-text declines). Task 6 below renders every plain-text final assistant response identically (as a normal reply); a muted "refusal" visual treatment is **not implemented** in this gate because there is no reliable way to detect it client-side without string-matching the model's own text, which is fragile and out of scope. This is a deliberate, recorded deviation from the table's "Refusal" row — see Task 6's note.

---

### Task 1: Panel state machine — status hook

**Files:**
- Create: `frontend/src/components/shell/agent-panel/use-panel-state.ts`

**Interfaces:**
- Produces: `type PanelState = "idle" | "thinking" | "streaming" | "approval" | "success" | "unavailable"`, and `usePanelState(chat: ReturnType<typeof useChat>): { state: PanelState; pendingApprovalPart: ToolUIPart | null }` — the classification logic every leaf component and the shell will read. `ToolUIPart` is `@ai-sdk/react`'s exported type for a message part with `type` starting `tool-`.

This task has no visual output — it is a pure function of `useChat`'s `messages` and `status`, split out so the classification logic (which state wins when) has one place to be correct, tested independently of any rendering.

- [ ] **Step 1: Write the failing test**

No test runner exists yet (see Global Constraints), so this task is verified by a throwaway Node script run by the developer, not a permanent test file. Write `frontend/src/components/shell/agent-panel/use-panel-state.ts` directly (Step 3) and verify via Step 4's manual check instead of a red/green cycle. This is the one task in this plan without a TDD step, called out explicitly rather than silently skipped.

- [ ] **Step 2: (skipped — see Step 1)**

- [ ] **Step 3: Implement `use-panel-state.ts`**

```ts
"use client";

import type { UIMessage } from "@ai-sdk/react";

/**
 * The six FRONTEND-PLAN.md states, minus "unavailable" (that one never reaches
 * useChat at all — it is rendered before a conversation exists, see agent-panel.tsx).
 */
export type PanelState = "idle" | "thinking" | "streaming" | "approval" | "success";

// Any part whose `type` starts with "tool-" carries this shape once a tool call
// is in flight — `@ai-sdk/react` types it per-tool-name, so this is the common
// subset every state and approval field share, per the tool-approvals docs
// (ai-sdk.dev/docs/agents/tool-approvals, checked 2026-08-13).
export interface ToolUIPart {
  type: string;
  toolCallId: string;
  state: "approval-requested" | "approval-responded" | "output-available" | "output-denied" | string;
  input?: Record<string, unknown>;
  output?: unknown;
  approval?: { id: string; approved?: boolean; isAutomatic?: boolean; reason?: string };
}

function toolParts(message: UIMessage | undefined): ToolUIPart[] {
  if (!message) return [];
  return message.parts.filter((part) => part.type.startsWith("tool-")) as unknown as ToolUIPart[];
}

/**
 * Classifies the panel's current state from useChat's own status and the last
 * message's parts. One function, so "which state wins" is decided in one place
 * rather than re-derived per leaf component and risking disagreement between them.
 */
export function classifyPanelState(
  status: "submitted" | "streaming" | "ready" | "error",
  messages: UIMessage[],
): { state: PanelState; pendingApprovalPart: ToolUIPart | null } {
  if (messages.length === 0) {
    return { state: "idle", pendingApprovalPart: null };
  }

  const last = messages[messages.length - 1];
  const parts = toolParts(last);
  const pending = parts.find((part) => part.state === "approval-requested" && !part.approval?.isAutomatic);

  if (pending) {
    return { state: "approval", pendingApprovalPart: pending };
  }

  const hasOutput = parts.some((part) => part.state === "output-available");
  if (hasOutput) {
    return { state: "success", pendingApprovalPart: null };
  }

  if (status === "submitted") {
    // Sent, nothing back yet — no text, no tool part.
    const hasAnyContent = last.parts.some((part) => part.type === "text" && part.text.length > 0);
    return { state: hasAnyContent ? "streaming" : "thinking", pendingApprovalPart: null };
  }

  if (status === "streaming") {
    return { state: "streaming", pendingApprovalPart: null };
  }

  // status is "ready" or "error" with a completed last message and no tool
  // output — a plain finished text reply, which includes refusals (see Global
  // Constraints: refusal has no distinct wire signal, so it renders as "streaming"
  // in its settled form — message-list.tsx's normal reply rendering covers this).
  return { state: "streaming", pendingApprovalPart: null };
}
```

- [ ] **Step 4: Verify manually**

Developer runs `npx tsc --noEmit` from `frontend/`. Expected: no errors mentioning `use-panel-state.ts`. (Full manual behavior verification happens in Task 8 once the panel is wired end to end — this step only confirms the file compiles.)

- [ ] **Step 5: Commit**

Hand off to developer: "Stage `frontend/src/components/shell/agent-panel/use-panel-state.ts` and commit with message `feat(frontend): agent panel state classifier (Gate 21 task 1)`."

---

### Task 2: Idle state + example chips

**Files:**
- Create: `frontend/src/components/shell/agent-panel/idle-state.tsx`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `IdleState({ onPickExample }: { onPickExample: (text: string) => void })` — a React component. `onPickExample` is called with the chip's text when clicked; the shell (Task 7) wires this to filling the input, not sending.

- [ ] **Step 1: Implement `idle-state.tsx`**

No test runner exists (Global Constraints) — this and every remaining rendering task skip the write-test/run-test steps and are verified together in Task 8's manual pass. Steps below are numbered to match the plan's convention but collapse to "implement" + "typecheck."

```tsx
"use client";

const EXAMPLES = [
  "What's low on stock right now?",
  "Add 8 units to Sourdough loaf 800g",
  "Create a new product for oat milk",
];

export function IdleState({ onPickExample }: { onPickExample: (text: string) => void }) {
  return (
    <div className="flex flex-col gap-stack">
      <p className="text-sm text-muted-foreground">
        Ask it to look something up or make a change. It can do exactly what the forms can do —
        nothing more.
      </p>
      <div className="flex flex-col gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => onPickExample(example)}
            className="rounded-(--radius) border border-border bg-secondary px-3 py-2 text-left text-sm text-secondary-foreground hover:bg-accent"
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Developer runs `npx tsc --noEmit` from `frontend/`. Expected: no errors mentioning `idle-state.tsx`.

- [ ] **Step 3: Commit**

Hand off: "Stage `frontend/src/components/shell/agent-panel/idle-state.tsx` and commit with message `feat(frontend): agent panel idle state (Gate 21 task 2)`."

---

### Task 3: Thinking indicator + keyframes

**Files:**
- Create: `frontend/src/components/shell/agent-panel/thinking-indicator.tsx`
- Modify: `frontend/src/app/globals.css` — add `shimmer` and `blink` keyframes (neither exists yet; confirmed by reading the file in full this session).

**Interfaces:**
- Consumes: nothing.
- Produces: `ThinkingIndicator()` — no props, a React component. Also produces the `blink` keyframe/utility that Task 5 (streaming cursor) consumes — defined here since this is the first task needing a CSS animation in this file.

- [ ] **Step 1: Add keyframes to `globals.css`**

Add after the existing `@layer base { ... }` block (after line 276, the closing brace of the `table, [data-numeric]` rule):

```css
@layer utilities {
  /*
   * Agent panel animations (Gate 21). Two states share these: the thinking
   * indicator's dots (shimmer) and the streaming reply's trailing cursor
   * (blink). Defined once here rather than per-component so both stay in sync
   * if the timing ever changes.
   */
  @keyframes shimmer {
    0%, 80%, 100% {
      opacity: 0.3;
    }
    40% {
      opacity: 1;
    }
  }

  @keyframes blink {
    0%, 50% {
      opacity: 1;
    }
    50.01%, 100% {
      opacity: 0;
    }
  }

  .animate-shimmer {
    animation: shimmer 1.4s ease-in-out infinite;
  }

  .animate-blink {
    animation: blink 1s step-end infinite;
  }
}
```

- [ ] **Step 2: Implement `thinking-indicator.tsx`**

```tsx
export function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <span>Thinking</span>
      <span className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-shimmer"
            style={{ animationDelay: `${i * 0.16}s` }}
          />
        ))}
      </span>
    </div>
  );
}
```

- [ ] **Step 3: Typecheck**

Developer runs `npx tsc --noEmit` from `frontend/`. Expected: no errors.

- [ ] **Step 4: Commit**

Hand off: "Stage `frontend/src/components/shell/agent-panel/thinking-indicator.tsx` and `frontend/src/app/globals.css`, commit with message `feat(frontend): agent panel thinking state + shared animations (Gate 21 task 3)`."

---

### Task 4: Message list (streaming reply + settled replies)

**Files:**
- Create: `frontend/src/components/shell/agent-panel/message-list.tsx`

**Interfaces:**
- Consumes: `UIMessage` type from `@ai-sdk/react`; `blink` keyframe/`.animate-blink` utility from Task 3.
- Produces: `MessageList({ messages, isStreaming }: { messages: UIMessage[]; isStreaming: boolean })` — renders every message's text parts; the last message gets a trailing blinking cursor appended only while `isStreaming` is true. Consumed by the shell (Task 7).

- [ ] **Step 1: Implement `message-list.tsx`**

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
    <div className="flex flex-col gap-stack overflow-y-auto">
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

- [ ] **Step 2: Typecheck**

Developer runs `npx tsc --noEmit` from `frontend/`. Expected: no errors. If `UIMessage`'s `parts` union does not narrow to `{ text: string }` on `type === "text"` cleanly, use `@ai-sdk/react`'s exported `TextUIPart` type instead of the inline cast — check `node_modules/@ai-sdk/react/dist/index.d.ts` for the exact export name at implementation time, since this wasn't verified against the installed package this session.

- [ ] **Step 3: Commit**

Hand off: "Stage `frontend/src/components/shell/agent-panel/message-list.tsx`, commit with message `feat(frontend): agent panel message list + streaming cursor (Gate 21 task 4)`."

---

### Task 5: Tool-call-in-progress card (Confirm/Cancel)

**Files:**
- Create: `frontend/src/components/shell/agent-panel/tool-call-card.tsx`

**Interfaces:**
- Consumes: `ToolUIPart` type from Task 1's `use-panel-state.ts`.
- Produces: `ToolCallCard({ part, onRespond }: { part: ToolUIPart; onRespond: (approved: boolean) => void })`. `onRespond` is called by Confirm (`true`)/Cancel (`false`); the shell (Task 7) wires this to `addToolApprovalResponse`.

This is "the state the whole design exists to protect" per `AGENT-PLAN.md` — the user must see the tool name and its arguments before anything runs, and nothing here calls the tool directly; it only reports the decision upward.

- [ ] **Step 1: Implement `tool-call-card.tsx`**

```tsx
"use client";

import type { ToolUIPart } from "./use-panel-state";

// "tool-adjust_stock" -> "adjust stock". Generic across every mutating tool —
// see Global Constraints: the allowlist is inverted, so a new tool must render
// without a hardcoded name.
function actionLabel(toolType: string): string {
  const name = toolType.replace(/^tool-/, "").replace(/_/g, " ");
  return `About to ${name}`;
}

export function ToolCallCard({
  part,
  onRespond,
}: {
  part: ToolUIPart;
  onRespond: (approved: boolean) => void;
}) {
  const input = part.input ?? {};

  return (
    <div className="flex flex-col gap-2 rounded-(--radius) border border-border bg-card p-3 text-sm">
      <div className="text-xs font-semibold uppercase text-muted-foreground">
        {actionLabel(part.type)}
      </div>
      <dl className="grid grid-cols-2 gap-x-2 gap-y-1" data-numeric>
        {Object.entries(input).map(([key, value]) => (
          <div key={key} className="contents">
            <dt className="text-muted-foreground">{key}</dt>
            <dd>{String(value)}</dd>
          </div>
        ))}
      </dl>
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={() => onRespond(true)}
          className="h-control rounded-(--radius) bg-primary px-3 text-sm text-primary-foreground"
        >
          Confirm
        </button>
        <button
          type="button"
          onClick={() => onRespond(false)}
          className="h-control rounded-(--radius) border border-input bg-card px-3 text-sm text-foreground"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
```

**Note on the `12 → 20 (+8)` delta format from FRONTEND-PLAN.md's table:** the tool's raw `input` (e.g. `{ sku: "RICE-5KG", quantity: 20 }` for `adjust_stock` — see `agent/tests/test_app.py`'s fixtures for the real shape) does not carry the *current* quantity, only the target. Rendering `12 → 20 (+8)` would require knowing the product's current stock, which is not in the tool call — it would need a lookup against `src/lib/api` before rendering the card. **Deferred, recorded here rather than guessed:** this task ships the generic key/value rendering above; a follow-up would fetch the product's current quantity via the typed API client (allowed — `src/lib/api` may call `fetch`) to compute the delta. Flagged for the developer to decide whether that lookup belongs in this gate or a follow-up.

- [ ] **Step 2: Typecheck**

Developer runs `npx tsc --noEmit` from `frontend/`. Expected: no errors.

- [ ] **Step 3: Commit**

Hand off: "Stage `frontend/src/components/shell/agent-panel/tool-call-card.tsx`, commit with message `feat(frontend): agent panel tool-call approval card (Gate 21 task 5)`."

---

### Task 6: Success card

**Files:**
- Create: `frontend/src/components/shell/agent-panel/success-card.tsx`

**Interfaces:**
- Consumes: `ToolUIPart` type from Task 1.
- Produces: `SuccessCard({ part }: { part: ToolUIPart })`.

- [ ] **Step 1: Implement `success-card.tsx`**

```tsx
"use client";

import Link from "next/link";
import type { ToolUIPart } from "./use-panel-state";

export function SuccessCard({ part }: { part: ToolUIPart }) {
  const input = part.input ?? {};
  const sku = typeof input.sku === "string" ? input.sku : undefined;

  return (
    <div className="flex flex-col gap-1 rounded-(--radius) border border-border bg-card p-3 text-sm">
      <div>Done — {String(part.output ?? "the change was applied")}.</div>
      {sku && (
        <Link href={`/products/${sku}`} className="text-primary hover:underline">
          View product →
        </Link>
      )}
      <div className="font-mono text-xs text-muted-foreground">updated_by: system</div>
    </div>
  );
}
```

**Note (recorded, not guessed):** the product detail route pattern (`/products/${sku}` above) is assumed from `docs/FRONTEND-PLAN.md`'s Gate 13c reference to "product detail." Verify the exact route segment (SKU vs numeric ID) against `frontend/src/app/products/` at implementation time — this plan does not re-derive it from a fresh read.

- [ ] **Step 2: Typecheck**

Developer runs `npx tsc --noEmit` from `frontend/`. Expected: no errors.

- [ ] **Step 3: Commit**

Hand off: "Stage `frontend/src/components/shell/agent-panel/success-card.tsx`, commit with message `feat(frontend): agent panel success state (Gate 21 task 6)`."

---

### Task 7: Wire the shell — `agent-panel.tsx`

**Files:**
- Modify: `frontend/src/components/shell/agent-panel.tsx` (full rewrite of the current 29-line static file).

**Interfaces:**
- Consumes: `classifyPanelState` from Task 1; `IdleState` (Task 2); `ThinkingIndicator` (Task 3); `MessageList` (Task 4); `ToolCallCard` (Task 5); `SuccessCard` (Task 6).
- Produces: `AgentPanel()` — same export name and same call site (`frontend/src/components/shell/nav.tsx` or wherever it's currently mounted — grep for `AgentPanel` usage before editing to confirm the import doesn't need updating).

- [ ] **Step 1: Confirm the mount point is unaffected**

Grep `frontend/src` for `AgentPanel` to confirm it's still a default named import with no props expected from the parent. If the parent passes no props today, none should be added — this component manages its own state internally (creating its own conversation on mount).

- [ ] **Step 2: Implement the rewritten `agent-panel.tsx`**

```tsx
"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, lastAssistantMessageIsCompleteWithApprovalResponses } from "ai";
import { useEffect, useState } from "react";

import { IdleState } from "./agent-panel/idle-state";
import { MessageList } from "./agent-panel/message-list";
import { SuccessCard } from "./agent-panel/success-card";
import { ThinkingIndicator } from "./agent-panel/thinking-indicator";
import { ToolCallCard } from "./agent-panel/tool-call-card";
import { classifyPanelState, type ToolUIPart } from "./agent-panel/use-panel-state";

/**
 * The agent region. Gate 20 gave the agent its own HTTP surface and a Next.js
 * proxy at /api/agent/[...path]; Gate 21 is this file — wiring useChat to that
 * proxy and rendering FRONTEND-PLAN.md's six states. The "unavailable" state
 * (Gate 13f) is superseded: the proxy is always considered configured once
 * this ships, since AGENT_BASE_URL not being set is a developer setup error
 * the proxy itself reports (see route.ts's 503 branch), not a state this
 * component distinguishes.
 */
export function AgentPanel() {
  const [conversationId, setConversationId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/agent/conversations", { method: "POST" })
      .then((response) => response.json())
      .then((data: { conversation_id: number }) => {
        if (!cancelled) setConversationId(data.conversation_id);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (conversationId === null) {
    return (
      <aside className="flex w-64 shrink-0 flex-col gap-stack border-l border-border bg-card p-section">
        <div className="text-sm font-semibold">Assistant</div>
        <div className="text-sm text-muted-foreground">Connecting…</div>
      </aside>
    );
  }

  return <ConnectedAgentPanel conversationId={conversationId} />;
}

function ConnectedAgentPanel({ conversationId }: { conversationId: number }) {
  const [input, setInput] = useState("");

  const { messages, sendMessage, addToolApprovalResponse, status } = useChat({
    id: String(conversationId),
    transport: new DefaultChatTransport({
      api: `/api/agent/conversations/${conversationId}/turns`,
    }),
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithApprovalResponses,
  });

  const { state, pendingApprovalPart } = classifyPanelState(status, messages);

  const submit = (text: string) => {
    if (text.trim().length === 0) return;
    sendMessage({ text });
    setInput("");
  };

  return (
    <aside className="flex w-64 shrink-0 flex-col gap-stack border-l border-border bg-card p-section">
      <div className="text-sm font-semibold">Assistant</div>

      <div className="flex-1 overflow-y-auto">
        {state === "idle" && <IdleState onPickExample={setInput} />}
        {state === "thinking" && <ThinkingIndicator />}
        {state === "streaming" && (
          <MessageList messages={messages} isStreaming={status === "streaming"} />
        )}
        {state === "approval" && pendingApprovalPart && (
          <>
            <MessageList messages={messages} isStreaming={false} />
            <ToolCallCard
              part={pendingApprovalPart}
              onRespond={(approved) =>
                addToolApprovalResponse({ id: pendingApprovalPart.approval!.id, approved })
              }
            />
          </>
        )}
        {state === "success" && (
          <>
            <MessageList messages={messages} isStreaming={false} />
            {(() => {
              const last = messages[messages.length - 1];
              const outputPart = last?.parts.find(
                (part): part is ToolUIPart =>
                  part.type.startsWith("tool-") &&
                  (part as ToolUIPart).state === "output-available",
              );
              return outputPart ? <SuccessCard part={outputPart} /> : null;
            })()}
          </>
        )}
      </div>

      <form
        className="mt-auto pt-stack"
        onSubmit={(event) => {
          event.preventDefault();
          submit(input);
        }}
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask the assistant…"
          className="h-control w-full rounded-(--radius) border border-input bg-card px-3 text-sm text-foreground"
        />
      </form>
    </aside>
  );
}
```

- [ ] **Step 3: Typecheck**

Developer runs `npx tsc --noEmit` from `frontend/`. Expected: no errors. `addToolApprovalResponse` and `lastAssistantMessageIsCompleteWithApprovalResponses`'s exact exported names were confirmed via Context7 docs this session (ai-sdk.dev/docs/agents/tool-approvals, ai-sdk.dev/docs/migration-guides/migration-guide-5-0) but not against the literal installed `.d.ts` — if either name doesn't resolve, check `node_modules/@ai-sdk/react/dist/index.d.ts` and `node_modules/ai/dist/index.d.ts` for the actual export before renaming anything silently; report back if they differ from what's written here.

- [ ] **Step 4: Lint**

Developer runs `npm run lint` from `frontend/`. Expected: clean — no `no-restricted-globals` (`fetch`) violation, since `agent-panel.tsx` is not `src/lib/api` and does call `fetch` directly for `POST /api/agent/conversations`. **This is a real risk, not a formality**: ESLint Rule 1 (`eslint.config.mjs` lines 87-107) restricts `fetch` to `src/lib/api/**` and the proxy route only — `agent-panel.tsx` is neither. If lint fails here, move the `POST /api/agent/conversations` call into a tiny helper under `src/lib/api` (e.g. `src/lib/api/agent.ts`, exporting `startAgentConversation(): Promise<number>`) and import that instead, since `useChat`'s own transport calls are exempt (they're a documented client library, not a raw `fetch` this codebase wrote) — but the conversation-creation call is still a `fetch` this codebase wrote, so it must go through the sanctioned path.

- [ ] **Step 5: Commit**

Hand off: "Stage `frontend/src/components/shell/agent-panel.tsx` and (if Step 4 required it) `frontend/src/lib/api/agent.ts`, commit with message `feat(frontend): wire agent panel to useChat and the six FRONTEND-PLAN.md states (Gate 21 task 7)`."

---

### Task 8: Manual verification + docs close-out

**Files:**
- Modify: `docs/PLAN.md` (progress table row 21).
- Modify: `docs/AGENT-PLAN.md` (Gate 21 section — fold in the amendments below, do not create a new doc).

**Interfaces:** none — this task is verification and documentation only.

- [ ] **Step 1: Developer starts both services**

Hand off exact commands:
```bash
# terminal 1, from backend/
uvicorn api.main:app --reload
# terminal 2, from agent/
python -m app   # or however app.py is currently run — check agent/README or scripts/ for the actual entrypoint; app.py itself has no __main__ block shown in this session's reads, confirm before handoff
# terminal 3, from frontend/
npm run dev
```
Expected: backend on :8000, agent service on :8002 (per `agent/app.py`'s `PORT` constant), frontend on :3000.

- [ ] **Step 2: Manual browser walkthrough**

Use chrome-devtools or playwright MCP (only after the developer confirms all three services are up, per the working agreement). Navigate to the app, open the agent panel, and exercise:
1. Idle state renders with 3 chips; clicking one fills the input without sending.
2. Sending a read-only question ("What's low on stock right now?") shows Thinking → a streamed reply with a visible cursor while streaming, settling to plain text.
3. Sending a mutating request ("Add 8 units to Sourdough loaf 800g" or equivalent, matched to real seed data) shows the tool-call-in-progress card with Confirm/Cancel.
4. Clicking Confirm resumes and shows the Success card with `updated_by: system` and a working "View product →" link.
5. Repeating the mutating request and clicking Cancel resumes without applying the change (verify in the product list/detail that stock did not change).
6. Reloading the browser mid-approval (after step 3, before confirming) re-shows the approval card (this exercises Gate 20's `save_pending`/`load_pending`, not new Gate 21 code, but is the first UI-visible proof it works).

Record the actual result of each numbered check against this list — if any step fails, that is a bug to fix in this gate, not a note for later.

- [ ] **Step 3: Update `docs/PLAN.md`'s progress table**

Change row 21 from whatever placeholder/pending state it currently shows to done, dated, with a one-line summary ("Agent panel wired to useChat; six states built; approval flow verified manually against a live agent service").

- [ ] **Step 4: Fold amendments into `docs/AGENT-PLAN.md`'s existing Gate 21 section**

Append to the existing Gate 21 section (do not create a new section) three findings from this session, matching the style of the Gate 20 close-out's numbered findings:

1. Approval wiring is native in `@ai-sdk/react` v4 — `useChat` returns `addToolApprovalResponse({id, approved})`, and tool parts carry `state: 'approval-requested' | 'approval-responded' | 'output-available' | 'output-denied'` with `part.approval.id`/`part.approval.approved`. No hand-rolled parsing of the wire protocol was needed on the client. Verified against ai-sdk.dev/docs/agents/tool-approvals, 2026-08-13.
2. Version floor re-checked against live npm on 2026-08-13: `ai@7.0.64` / `@ai-sdk/react@4.0.67` unchanged since the Gate 20 close-out's finding.
3. The resumability deferral's "revisit" note from this section is closed as a no-op: Gate 20's `store.save_pending`/`load_pending` already covers the pause-for-approval case, which is the only turn-duration-observable scenario in scope. No new persistence work landed at this gate.

Also record the two deviations found during planning, so they are decisions rather than silent gaps:
- The `12 → 20 (+8)` delta format from `FRONTEND-PLAN.md`'s table needs the product's pre-change quantity, which is not present in a tool call's `input`. Shipped instead: generic key/value rendering of the raw tool arguments. Computing the real delta would need a lookup via `src/lib/api` before rendering — deferred, not built.
- The "Refusal" state has no distinct wire signal (no `state: 'refused'` or equivalent) — a plain-text decline is indistinguishable, at the wire level, from any other plain-text final reply. Shipped instead: all plain-text replies render identically. A muted "refusal" treatment was not built because there is no non-fragile way to detect it client-side.

- [ ] **Step 5: Final commit handoff**

Hand off: "Stage `docs/PLAN.md` and `docs/AGENT-PLAN.md`, commit with message `docs(agent): close Gate 21 — frontend panel wired, two deviations recorded`."
