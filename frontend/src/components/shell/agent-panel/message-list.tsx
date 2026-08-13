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
