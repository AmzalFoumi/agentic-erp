"use client";

import Link from "next/link";
import type { ToolUIPart } from "./use-panel-state";

/**
 * Who the ERP recorded as having made this change.
 *
 * ⚠️ **This line used to be the hardcoded string `updated_by: system`.** That
 * was accurate at gate 13, when `SystemActor` was the only actor that existed,
 * and it quietly became a lie at gate 25 when the agent started acting as the
 * signed-in person. It is printed in exactly the place someone looks to check
 * that the audit trail worked, so a wrong value here is worse than no value:
 * it reads as proof that delegation failed when it succeeded.
 *
 * It now comes from the tool's own output — `updated_by` in
 * `backend/mcp_server/server.py`'s `_describe()` — so it cannot drift from what
 * is actually in the database. If it ever disagrees with the row again, the
 * fix is upstream, not another literal here.
 *
 * `part.output` is whatever the tool returned, so its shape is not guaranteed:
 * a JSON string, a parsed object, or a plain sentence from a tool that does not
 * return a product. Anything unreadable yields `undefined` and the line is
 * simply not rendered — a confirmation card must not become an error because a
 * label was missing.
 */
function updatedBy(output: unknown): string | undefined {
  let value = output;

  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return undefined;
    }
  }

  if (typeof value !== "object" || value === null) return undefined;

  const who = (value as Record<string, unknown>).updated_by;
  return typeof who === "string" && who ? who : undefined;
}

export function SuccessCard({ part }: { part: ToolUIPart }) {
  const input = part.input ?? {};
  const sku = typeof input.sku === "string" ? input.sku : undefined;
  const who = updatedBy(part.output);

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
}
