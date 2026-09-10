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
              <dd>{value == null ? "—" : String(value)}</dd>
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
