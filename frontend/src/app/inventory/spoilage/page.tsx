import { ApiErrorState } from "@/components/domain/api-error-state";
import { api } from "@/lib/api/client";

import { SpoilageTable } from "./_components/spoilage-table";

/**
 * Stock about to expire, and what discounting it would recover.
 *
 * A Server Component that awaits the fetch, matching /products and /approvals.
 * No pagination: the list is "what expires in the next couple of days", which
 * is a handful of lots in a shop of any size.
 *
 * ⚠️ The scan horizon is deliberately NOT a query parameter on this page. The
 * backend defaults it to the discount ladder's own reach, so the screen and
 * the shop's pricing policy cannot drift apart — widen the ladder in
 * `services/pricing.py` and this screen follows automatically.
 */
export default async function SpoilagePage() {
  const { data, error } = await api.GET("/inventory/spoilage", {});

  if (error) {
    return (
      <ApiErrorState title="Couldn't load the spoilage report" detail={error.detail} />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-section shrink-0">
        <h1 className="text-lg font-semibold">Expiring soon</h1>
        <p className="text-sm text-muted-foreground">
          Stock close to its expiry date, with the discount the shop&apos;s
          pricing policy would apply. Nothing here is discounted yet.
        </p>
      </div>

      {data.items.length === 0 ? (
        <div className="rounded-(--radius) border border-dashed border-border p-16 text-center">
          <div className="text-sm font-semibold">Nothing expiring</div>
          <div className="mt-1 text-sm text-muted-foreground">
            No stock is within {data.within_days} day
            {data.within_days === 1 ? "" : "s"} of its expiry date. Stock with no
            recorded expiry date is not counted here — nobody knows when it goes
            off, so it cannot be marked down.
          </div>
        </div>
      ) : (
        <SpoilageTable report={data} />
      )}
    </div>
  );
}
