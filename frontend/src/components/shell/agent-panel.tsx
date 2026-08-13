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
import { startAgentConversation } from "@/lib/api/agent";

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
    startAgentConversation().then((id) => {
      if (!cancelled) setConversationId(id);
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
