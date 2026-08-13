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

  // useChat optimistically appends the user's own message and sets status to
  // "submitted" before any assistant message exists. If the last message
  // isn't from the assistant yet, there's nothing to inspect for tool parts
  // or output — the agent hasn't responded at all, so this is "thinking".
  if (last.role !== "assistant") {
    return { state: "thinking", pendingApprovalPart: null };
  }

  const parts = toolParts(last);
  const pending = parts.find(
    (part) => part.state === "approval-requested" && !part.approval?.isAutomatic && part.approval?.id,
  );

  if (pending) {
    return { state: "approval", pendingApprovalPart: pending };
  }

  // Only an approved, human-confirmed mutation counts as "success". Read-only
  // tools (list_products, get_product, ...) never go through approval — they
  // reach "output-available" too, but with no `approval` object at all, so
  // they fall through to the normal reply rendering instead of the mutation
  // Success card. No tool name is hardcoded here (Global Constraint).
  const hasApprovedOutput = parts.some(
    (part) => part.state === "output-available" && part.approval?.approved === true,
  );
  if (hasApprovedOutput) {
    return { state: "success", pendingApprovalPart: null };
  }

  if (status === "submitted" || status === "streaming") {
    return { state: "streaming", pendingApprovalPart: null };
  }

  // status is "ready" or "error" with a completed last message and no tool
  // output — a plain finished text reply, which includes refusals (see Global
  // Constraints: refusal has no distinct wire signal, so it renders as "streaming"
  // in its settled form — message-list.tsx's normal reply rendering covers this).
  return { state: "streaming", pendingApprovalPart: null };
}
