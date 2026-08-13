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
        <Link href={`/products?search=${encodeURIComponent(sku)}`} className="text-primary hover:underline">
          View product →
        </Link>
      )}
      <div className="font-mono text-xs text-muted-foreground">updated_by: system</div>
    </div>
  );
}
