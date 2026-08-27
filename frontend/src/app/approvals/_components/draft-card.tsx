"use client";

import { useState, useTransition } from "react";

import { MoneyDisplay } from "@/components/domain/money-display";
import { Badge } from "@/components/ui/badge";
import type { components } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

import { approveDraft, rejectDraft } from "../actions";

type Draft = components["schemas"]["DraftRead"];

/**
 * Human wording for each kind of proposal.
 *
 * A lookup rather than a formatted `draft_type` string, because "BATCH PRICE
 * MARKDOWN" is not what a manager should be asked to read. An unrecognised
 * type falls back to the raw name rather than throwing — a proposal the UI has
 * not learned about yet must still be readable and rejectable, since the
 * alternative is a row nobody can clear.
 */
const TYPE_LABELS: Record<string, string> = {
  BATCH_PRICE_MARKDOWN: "Markdown expiring stock",
  DELIVERY_RECONCILIATION: "Delivery discrepancy",
  PURCHASE_ORDER_CREATE: "Purchase order",
};

/**
 * Where a proposal came from, in words.
 *
 * The value is on the wire because provenance is the point of the queue: the
 * whole feature is "the agent suggested this, a human decided it", and hiding
 * which half was which would make the screen a to-do list instead.
 */
const SOURCE_LABELS: Record<string, string> = {
  mcp_agent: "Proposed by the assistant",
  web_ui: "Proposed from the web app",
  system: "Proposed automatically",
};

export function DraftCard({ draft }: { draft: Draft }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function decide(action: () => Promise<{ error: string } | null>) {
    setError(null);
    startTransition(async () => {
      const result = await action();
      if (result) setError(result.error);
    });
  }

  // Read off the API, never recomputed from expires_at. Same rule as
  // needs_reorder on products: the backend ships the answer so that the UI and
  // the agent cannot disagree about it.
  const expired = draft.is_expired;

  return (
    <article className="rounded-(--radius) border border-border bg-card p-4">
      <header className="mb-stack flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">
            {TYPE_LABELS[draft.draft_type] ?? draft.draft_type}
          </h2>
          <p className="text-xs text-muted-foreground">
            {SOURCE_LABELS[draft.created_via] ?? draft.created_via} ·{" "}
            {formatDateTime(draft.created_at)}
          </p>
        </div>
        {expired && (
          <Badge
            variant="outline"
            className="border-transparent bg-stock-out-surface text-stock-out"
          >
            Expired
          </Badge>
        )}
      </header>

      <p className="mb-stack text-sm text-foreground">{draft.reasoning}</p>

      {/*
        Two figures side by side, never netted into one. "We saved 12,000" and
        "we were about to lose 40,000 and recovered 12,000" are different
        sentences to a manager, and only one of them is the truth.
        Rendered only when present: null means this kind of proposal has no
        financial dimension, which is not the same as zero.
      */}
      {(draft.cost_at_risk ?? draft.projected_recovery) !== null && (
        <dl className="mb-stack flex gap-8 text-sm">
          {draft.cost_at_risk !== null && (
            <div>
              <dt className="text-xs text-muted-foreground">At risk</dt>
              <dd className="text-stock-out">
                <MoneyDisplay value={draft.cost_at_risk} />
              </dd>
            </div>
          )}
          {draft.projected_recovery !== null && (
            <div>
              <dt className="text-xs text-muted-foreground">Recovered if approved</dt>
              <dd className="text-stock-ok">
                <MoneyDisplay value={draft.projected_recovery} />
              </dd>
            </div>
          )}
        </dl>
      )}

      <details className="mb-stack">
        <summary className="cursor-pointer text-xs text-muted-foreground">
          Show the full proposal
        </summary>
        {/*
          The raw payload. Deliberately not prettified into a bespoke view per
          draft type: a manager approving something should be able to see
          exactly what will be sent, and a summary that omits a field is worse
          than no summary. Per-type views can come later, in addition to this.
        */}
        <pre className="mt-2 overflow-x-auto rounded-(--radius) bg-muted p-3 text-xs">
          {JSON.stringify(draft.payload, null, 2)}
        </pre>
      </details>

      {error && (
        <p className="mb-stack text-sm text-stock-out" role="alert">
          {error}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          disabled={pending || expired}
          onClick={() => decide(() => approveDraft(draft.id))}
          className="h-control flex items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {pending ? "Working…" : "Approve and run"}
        </button>
        <button
          type="button"
          disabled={pending || expired}
          onClick={() => decide(() => rejectDraft(draft.id))}
          className="h-control flex items-center rounded-(--radius) border border-border px-4 text-sm disabled:opacity-50"
        >
          Reject
        </button>
      </div>

      {expired && (
        <p className="mt-stack text-xs text-muted-foreground">
          This proposal passed its deadline and can no longer be run. The
          numbers behind it are from{" "}
          {draft.expires_at ? formatDateTime(draft.expires_at) : "earlier"} and
          may have moved since — ask the assistant for a fresh one.
        </p>
      )}
    </article>
  );
}
