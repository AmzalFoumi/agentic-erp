"use client";

import type { ToolUIPart } from "./use-panel-state";
import { Button } from "@/components/ui/button";

// "tool-adjust_stock" -> "adjust stock". Generic across every mutating tool —
// see Global Constraints: the allowlist is inverted, so a new tool must render
// without a hardcoded name.
function actionLabel(toolType: string): string {
  const name = toolType.replace(/^tool-/, "").replace(/_/g, " ");
  return `About to ${name}`;
}

export function ToolCallCard({
  part,
  onRespond,
}: {
  part: ToolUIPart;
  onRespond: (approved: boolean) => void;
}) {
  const input = part.input ?? {};

  return (
    <div className="flex flex-col gap-2 rounded-(--radius) border border-border bg-card p-3 text-sm">
      <div className="text-xs font-semibold uppercase text-muted-foreground">
        {actionLabel(part.type)}
      </div>
      <dl className="grid grid-cols-2 gap-x-2 gap-y-1" data-numeric>
        {Object.entries(input).map(([key, value]) => (
          <div key={key} className="contents">
            <dt className="text-muted-foreground">{key}</dt>
            <dd>{String(value)}</dd>
          </div>
        ))}
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
