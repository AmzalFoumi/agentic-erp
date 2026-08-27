"use client";

import { useState, useTransition } from "react";

import { MoneyDisplay } from "@/components/domain/money-display";
import { Badge } from "@/components/ui/badge";
import type { components } from "@/lib/api/client";
import { formatDate, formatDaysRemaining } from "@/lib/format";

import { proposeMarkdown } from "../actions";

type Report = components["schemas"]["SpoilageReportRead"];

/**
 * The urgency colour for one row.
 *
 * Driven by `days_remaining`, which the **server** calculated. Deriving it in
 * the browser would mean using the viewer's clock, and two people in two
 * timezones must not disagree about whether stock expires today.
 */
function urgency(days: number) {
  if (days <= 0) return { className: "bg-stock-out-surface text-stock-out", label: "Now" };
  if (days === 1) return { className: "bg-stock-low-surface text-stock-low", label: "Urgent" };
  return { className: "bg-muted text-muted-foreground", label: "Soon" };
}

export function SpoilageTable({ report }: { report: Report }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [staged, setStaged] = useState<number | null>(null);

  function propose() {
    setError(null);
    startTransition(async () => {
      const result = await proposeMarkdown();
      if ("error" in result) setError(result.error);
      else setStaged(result.draftId);
    });
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/*
        The two totals, side by side and never netted into one number.

        "At risk" is money the shop has already spent and loses entirely if
        this stock is thrown away. "Recovered if approved" is a forecast that
        assumes the discounted stock actually sells. Subtracting one from the
        other would present a guess with the confidence of a fact, so the UI
        does not do it and the API does not offer a field for it.
      */}
      <dl className="mb-section flex shrink-0 gap-8">
        <div>
          <dt className="text-xs text-muted-foreground">At risk if nothing is done</dt>
          <dd className="text-lg text-stock-out">
            <MoneyDisplay value={report.total_cost_at_risk} />
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Recovered if all discounted stock sells</dt>
          <dd className="text-lg text-stock-ok">
            <MoneyDisplay value={report.total_projected_recovery} />
          </dd>
        </div>
      </dl>

      {error && (
        <p className="mb-stack shrink-0 text-sm text-stock-out" role="alert">
          {error}
        </p>
      )}

      {staged !== null && (
        <p className="mb-stack shrink-0 rounded-(--radius) border border-border bg-muted p-3 text-sm">
          Staged as proposal #{staged}. Nothing has changed yet —{" "}
          <a href="/approvals" className="underline">
            approve it on the Approvals screen
          </a>{" "}
          to apply these prices.
        </p>
      )}

      <div className="mb-section shrink-0">
        <button
          type="button"
          onClick={propose}
          disabled={pending || staged !== null}
          className="h-control flex items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {pending ? "Staging…" : "Propose these markdowns"}
        </button>
        {/*
          Said plainly next to the button rather than in a tooltip. The single
          most important thing about this screen is that pressing the button
          changes no price — a manager who believes otherwise will either avoid
          it or be alarmed by it.
        */}
        <p className="mt-1 text-xs text-muted-foreground">
          This stages a proposal for approval. No price changes until someone
          approves it.
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-auto rounded-(--radius) border border-border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-card">
            <tr className="border-b border-border text-left">
              <th className="p-3 font-medium">Product</th>
              <th className="p-3 font-medium">Lot</th>
              <th className="p-3 font-medium">Expires</th>
              <th className="p-3 text-right font-medium">Qty</th>
              <th className="p-3 text-right font-medium">Now</th>
              <th className="p-3 text-right font-medium">Proposed</th>
              <th className="p-3 text-right font-medium">At risk</th>
              <th className="p-3 text-right font-medium">Recovered</th>
            </tr>
          </thead>
          <tbody>
            {report.items.map((item) => {
              const tone = urgency(item.days_remaining);
              return (
                <tr key={item.lot_id} className="border-b border-border last:border-0">
                  <td className="p-3">
                    <div className="font-medium">{item.product_name}</div>
                    <div className="text-xs text-muted-foreground">{item.sku}</div>
                  </td>
                  <td className="p-3 text-xs text-muted-foreground">{item.lot_code}</td>
                  <td className="p-3">
                    <Badge variant="outline" className={`border-transparent ${tone.className}`}>
                      {tone.label}
                    </Badge>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {formatDate(item.expiry_date)} ·{" "}
                      {formatDaysRemaining(item.days_remaining)}
                    </div>
                  </td>
                  <td className="p-3 text-right tabular-nums">{item.quantity}</td>
                  <td className="p-3 text-right text-muted-foreground line-through">
                    <MoneyDisplay value={item.current_price} />
                  </td>
                  <td className="p-3 text-right">
                    <MoneyDisplay value={item.proposed_price} />
                    <div className="text-xs text-muted-foreground">
                      −{item.discount_percent}%
                    </div>
                  </td>
                  <td className="p-3 text-right text-stock-out">
                    <MoneyDisplay value={item.cost_at_risk} />
                  </td>
                  <td className="p-3 text-right text-stock-ok">
                    <MoneyDisplay value={item.projected_recovery} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
