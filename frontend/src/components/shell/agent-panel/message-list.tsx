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
