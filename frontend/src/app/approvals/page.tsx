import { ApiErrorState } from "@/components/domain/api-error-state";
import { api } from "@/lib/api/client";

import { DraftCard } from "./_components/draft-card";

const LIMIT = 50;

/**
 * The approval queue: proposals the assistant has staged, waiting for a human.
 *
 * A Server Component that awaits the fetch, matching /products. The queue is
 * short by construction — it is a list of things somebody is about to read —
 * so there is no pagination control, and `LIMIT` exists only so a runaway
 * proposer cannot render ten thousand cards.
 */
export default async function ApprovalsPage() {
  // A thrown network failure (no response at all) propagates to error.tsx,
  // which is the "backend unreachable" state. Only a real ErrorResponse is
  // handled inline. Never render an empty queue to paper over either — an
  // empty list here means "nothing to decide", which is a reassuring and
  // potentially false statement.
  const { data, error } = await api.GET("/drafts", {
    params: { query: { status: "pending", limit: LIMIT, offset: 0 } },
  });

  if (error) {
    return (
      <ApiErrorState title="Couldn't load the approval queue" detail={error.detail} />
    );
  }

  const { items } = data;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-section shrink-0">
        <h1 className="text-lg font-semibold">Approvals</h1>
        <p className="text-sm text-muted-foreground">
          Changes the assistant has proposed. Nothing here has happened yet.
        </p>
      </div>

      {items.length === 0 ? (
        <div className="rounded-(--radius) border border-dashed border-border p-16 text-center">
          <div className="text-sm font-semibold">Nothing waiting</div>
          <div className="mt-1 text-sm text-muted-foreground">
            When the assistant proposes a change — marking down stock that is
            about to expire, or raising an order — it appears here for you to
            approve.
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-stack">
          {items.map((draft) => (
            <DraftCard key={draft.id} draft={draft} />
          ))}
        </div>
      )}
    </div>
  );
}
