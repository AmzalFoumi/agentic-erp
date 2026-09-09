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
