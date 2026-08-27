"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { MoneyDisplay } from "@/components/domain/money-display";
import { Badge } from "@/components/ui/badge";
import type { components } from "@/lib/api/client";

import { proposeReorder } from "../actions";

type ReorderBundle = components["schemas"]["ReorderBundleRead"];

/**
 * One supplier's proposed order.
 *
 * Three things this component must get right, because they are the whole
 * point of the bundler rather than incidental UI:
 *
 *   1. A top-up line must not read as something that ran out — it is here
 *      only to reach the supplier's minimum.
 *   2. below_minimum is stated in words, with the shortfall, never just a
 *      number a manager has to interpret.
 *   3. The propose button posts nothing but the supplier id and reasoning —
 *      see actions.ts for why.
 */
export function BundleCard({ bundle }: { bundle: ReorderBundle }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const lowCount = bundle.lines.filter((line) => !line.is_top_up).length;
  const topUpCount = bundle.lines.length - lowCount;

  function propose() {
    setError(null);
    const reasoning = `${lowCount} product(s) at or below their reorder level from ${bundle.supplier_name}${
      topUpCount ? `, plus ${topUpCount} added to reach their minimum order` : ""
    }. Lead time ${bundle.lead_time_days} day(s).`;

    startTransition(async () => {
      const result = await proposeReorder(bundle.supplier_id, reasoning);
      if ("error" in result) {
        setError(result.error);
      } else {
        router.push("/approvals");
      }
    });
  }

  return (
    <article className="rounded-(--radius) border border-border bg-card p-4">
      <header className="mb-stack flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">{bundle.supplier_name}</h2>
          <p className="text-xs text-muted-foreground">
            Lead time {bundle.lead_time_days} day{bundle.lead_time_days === 1 ? "" : "s"}
          </p>
        </div>
        <div className="text-right">
          <div className="text-sm font-semibold">
            <MoneyDisplay value={bundle.bundle_value} />
          </div>
          <div className="text-xs text-muted-foreground">
            of <MoneyDisplay value={bundle.minimum_order_value} /> minimum
          </div>
        </div>
      </header>

      {/*
        Stated plainly, with the shortfall — not just a boolean a manager has
        to interpret. "Nothing left to add" is the truth: the top-up pass
        already tried every other product this supplier stocks.
      */}
      {bundle.below_minimum && (
        <p className="mb-stack rounded-(--radius) border border-stock-low/30 bg-stock-low-surface px-3 py-2 text-sm text-stock-low">
          Still <MoneyDisplay value={bundle.shortfall} /> below {bundle.supplier_name}
          &apos;s minimum — there is nothing else to add.
        </p>
      )}

      <ul className="mb-stack flex flex-col gap-1">
        {bundle.lines.map((line) => (
          <li
            key={line.product_id}
            className={`flex items-center justify-between rounded-(--radius) px-2 py-1 text-sm ${
              line.is_top_up ? "bg-muted" : ""
            }`}
          >
            <span className="flex items-center gap-2">
              {line.name}
              {line.is_top_up && (
                <Badge
                  variant="outline"
                  className="border-transparent bg-secondary text-xs text-muted-foreground"
                >
                  Added to reach minimum
                </Badge>
              )}
            </span>
            <span className="flex items-center gap-3 text-muted-foreground">
              <span data-numeric className="font-mono">
                {line.quantity}
              </span>
              <MoneyDisplay value={line.line_total} />
            </span>
          </li>
        ))}
      </ul>

      {error && (
        <p className="mb-stack text-sm text-stock-out" role="alert">
          {error}
        </p>
      )}

      <button
        type="button"
        disabled={pending}
        onClick={propose}
        className="h-control flex items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
      >
        {pending ? "Proposing…" : "Propose this order"}
      </button>
    </article>
  );
}
