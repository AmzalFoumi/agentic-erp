"use client";

import { useEffect, useState } from "react";

import type { ToolUIPart } from "./use-panel-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getProductSummary } from "@/lib/api/products";

// "tool-adjust_stock" -> "adjust stock". Generic across every mutating tool —
// see Global Constraints: the allowlist is inverted, so a new tool must render
// without a hardcoded name.
function actionLabel(toolType: string): string {
  const name = toolType.replace(/^tool-/, "").replace(/_/g, " ");
  return `About to ${name}`;
}

// The tool's real parameter name is `product_id` (see mcp_server/server.py's
// update_product/adjust_stock signatures) — a raw id is what the model
// actually sends, not a display choice. Resolved to a SKU here, client-side,
// rather than asking the model to look it up first: it already has the id
// and asking it to fetch-then-decide would cost a round trip for something
// purely cosmetic.
function useProductLabel(productId: unknown): string | null | undefined {
  // Keyed by id so a stale in-flight lookup for a previous id never
  // overwrites the current one — same effect as the `cancelled` flag this
  // replaced, without needing a resetting `setLabel(undefined)` call inside
  // the effect body.
  const [resolved, setResolved] = useState<Record<number, string | null>>({});

  useEffect(() => {
    if (typeof productId !== "number" || productId in resolved) {
      return;
    }
    getProductSummary(productId).then((summary) => {
      setResolved((prev) => ({
        ...prev,
        [productId]: summary ? `${summary.sku} — ${summary.name}` : null,
      }));
    });
  }, [productId, resolved]);

  if (typeof productId !== "number") {
    return null;
  }
  return productId in resolved ? resolved[productId] : undefined;
}

export function ToolCallCard({
  part,
  onRespond,
}: {
  part: ToolUIPart;
  onRespond: (approved: boolean) => void;
}) {
  const input = part.input ?? {};
  const productLabel = useProductLabel((input as Record<string, unknown>).product_id);

  return (
    <div className="flex flex-col gap-2 rounded-(--radius) border border-border bg-card p-3 text-sm">
      <div className="text-xs font-semibold uppercase text-muted-foreground">
        {actionLabel(part.type)}
      </div>
      <dl className="grid grid-cols-2 gap-x-2 gap-y-1" data-numeric>
        {Object.entries(input).map(([key, value]) => {
          if (key === "product_id") {
            return (
              <div key={key} className="contents">
                <dt className="text-muted-foreground">product</dt>
                <dd data-numeric={false}>
                  {productLabel === undefined ? (
                    <Skeleton className="h-4 w-32" />
                  ) : (
                    productLabel ?? String(value)
                  )}
                </dd>
              </div>
            );
          }
          return (
            <div key={key} className="contents">
              <dt className="text-muted-foreground">{key}</dt>
              <dd>{String(value)}</dd>
            </div>
          );
        })}
      </dl>
      <div className="flex gap-2 pt-1">
        <Button type="button" onClick={() => onRespond(true)}>
          Confirm
        </Button>
        <Button type="button" variant="outline" onClick={() => onRespond(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
