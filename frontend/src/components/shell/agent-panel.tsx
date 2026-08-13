"use client";

import { useChat, type UIMessage } from "@ai-sdk/react";
import { DefaultChatTransport, lastAssistantMessageIsCompleteWithApprovalResponses } from "ai";
import { useEffect, useRef, useState } from "react";

import { IdleState } from "./agent-panel/idle-state";
import { MessageList } from "./agent-panel/message-list";
import { SuccessCard } from "./agent-panel/success-card";
import { ThinkingIndicator } from "./agent-panel/thinking-indicator";
import { ToolCallCard } from "./agent-panel/tool-call-card";
import { classifyPanelState, type ToolUIPart } from "./agent-panel/use-panel-state";
import { getAgentConversation, startAgentConversation } from "@/lib/api/agent";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// localStorage key holding the id of the conversation currently open in the
// panel, so a page reload can resume it (parked approval or plain history)
// instead of silently starting a brand-new conversation. No TTL/sweeper by
// design — a stale id just 404s and the code falls back to a fresh one.
const CONVERSATION_STORAGE_KEY = "agent-panel-conversation-id";

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
  const [initialMessages, setInitialMessages] = useState<UIMessage[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function resumeOrStart() {
      const storedId = window.localStorage.getItem(CONVERSATION_STORAGE_KEY);
      const parsedId = storedId ? Number(storedId) : null;

      if (parsedId !== null && Number.isFinite(parsedId)) {
        const existing = await getAgentConversation(parsedId);
        if (existing) {
          if (!cancelled) {
            setInitialMessages(existing.messages as UIMessage[]);
            setConversationId(parsedId);
          }
          return;
        }
        // 404 — the stored id no longer exists server-side. Fall through to
        // starting a fresh conversation below.
      }

      const newId = await startAgentConversation();
      if (!cancelled) {
        window.localStorage.setItem(CONVERSATION_STORAGE_KEY, String(newId));
        setConversationId(newId);
      }
    }

    resumeOrStart().catch((err: unknown) => {
      if (!cancelled) {
        setError(err instanceof Error ? err.message : "Failed to start agent conversation");
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  if (conversationId === null) {
    return (
      <aside className="flex h-full w-64 min-h-0 shrink-0 flex-col gap-stack border-l border-border bg-card p-section">
        <div className="text-sm font-semibold">Assistant</div>
        {error ? (
          <div className="text-sm text-destructive">{error}</div>
        ) : (
          <div className="text-sm text-muted-foreground">Connecting…</div>
        )}
      </aside>
    );
  }

  return <ConnectedAgentPanel conversationId={conversationId} initialMessages={initialMessages} />;
}

function ConnectedAgentPanel({
  conversationId,
  initialMessages,
}: {
  conversationId: number;
  initialMessages: UIMessage[];
}) {
  const [input, setInput] = useState("");

  const { messages, sendMessage, addToolApprovalResponse, status, error } = useChat({
    id: String(conversationId),
    messages: initialMessages,
    transport: new DefaultChatTransport({
      api: `/api/agent/conversations/${conversationId}/turns`,
    }),
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithApprovalResponses,
  });

  const { state, pendingApprovalPart } = classifyPanelState(status, messages);

  const [refetchError, setRefetchError] = useState<string | null>(null);
  const [isRefetching, setIsRefetching] = useState(false);

  const handleRefetch = async () => {
    setIsRefetching(true);
    setRefetchError(null);
    try {
      const existing = await getAgentConversation(conversationId);
      if (!existing) {
        setRefetchError("Conversation no longer exists");
      }
    } catch (err: unknown) {
      setRefetchError(err instanceof Error ? err.message : "Failed to refetch conversation");
    } finally {
      setIsRefetching(false);
    }
  };

  const submit = (text: string) => {
    if (text.trim().length === 0) return;
    sendMessage({ text });
    setInput("");
  };

  const last = messages[messages.length - 1];
  const lastHasVisibleText = (last?.parts ?? []).some(
    (part) => part.type === "text" && (part as { text: string }).text.length > 0,
  );

  // Covers two gaps in the raw wire signal: (1) right after the user's own
  // message is appended, `status` is already "submitted" but nothing has
  // streamed yet - the plain "thinking" case; (2) right after an approval is
  // confirmed, `status` goes "streaming" again for the tool-execution-and-reply
  // leg, but there is no growing text part until the model's final reply
  // starts, so the panel would otherwise show nothing at all in between.
  const showThinking =
    state === "thinking" || (state === "streaming" && !lastHasVisibleText);

  const scrollRef = useRef<HTMLDivElement>(null);

  // Keep the latest message in view as it arrives, instead of leaving the
  // scroll position wherever it was and making the user scroll down to see
  // a reply, an approval card, or the success card that just appeared.
  // Depends on text content too, not just message identity/count: a
  // streaming assistant message keeps the same id while its text grows, and
  // that growth is exactly when the bottom keeps moving out of view.
  const lastText = last?.parts
    .filter((part) => part.type === "text")
    .map((part) => (part as { text: string }).text)
    .join("");
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages.length, lastText, state, pendingApprovalPart]);

  return (
    <aside className="flex h-full w-64 min-h-0 shrink-0 flex-col gap-stack border-l border-border bg-card p-section">
      <div className="text-sm font-semibold">Assistant</div>

      <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col gap-stack overflow-y-auto">
        {state === "idle" && <IdleState onPickExample={setInput} />}
        {messages.length > 0 && (
          <MessageList messages={messages} isStreaming={status === "streaming"} />
        )}
        {showThinking && <ThinkingIndicator />}
        {state === "approval" && pendingApprovalPart && (
          <ToolCallCard
            part={pendingApprovalPart}
            onRespond={(approved) => {
              if (pendingApprovalPart.approval?.id) {
                addToolApprovalResponse({ id: pendingApprovalPart.approval.id, approved });
              }
            }}
          />
        )}
        {state === "success" &&
          (() => {
            const outputPart = last?.parts
              .filter((part) => part.type.startsWith("tool-"))
              .findLast((part) => {
                const toolPart = part as unknown as ToolUIPart;
                return toolPart.state === "output-available" && toolPart.approval?.approved === true;
              }) as ToolUIPart | undefined;
            return outputPart ? <SuccessCard part={outputPart} /> : null;
          })()}
        {status === "error" && (
          <div className="flex flex-col gap-2 rounded-(--radius) border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <div className="font-semibold">Error</div>
            <div>{error?.message ?? "An error occurred"}</div>
            {refetchError && <div className="text-xs">Refetch failed: {refetchError}</div>}
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={handleRefetch}
              disabled={isRefetching}
              className="mt-1"
            >
              {isRefetching ? "Refetching…" : "Retry"}
            </Button>
          </div>
        )}
      </div>

      <form
        className="mt-auto flex shrink-0 gap-2 pt-stack"
        onSubmit={(event) => {
          event.preventDefault();
          submit(input);
        }}
      >
        <Input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask the assistant…"
          aria-label="Message to assistant"
          className="min-w-0 flex-1"
        />
        <Button type="submit" disabled={input.trim().length === 0}>
          Send
        </Button>
      </form>
    </aside>
  );
}
