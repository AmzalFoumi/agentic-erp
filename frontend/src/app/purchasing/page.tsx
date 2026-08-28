import Link from "next/link";

import { ApiErrorState } from "@/components/domain/api-error-state";
import { api } from "@/lib/api/client";

import { BundleCard } from "./_components/bundle-card";

/**
 * What to buy today, grouped by supplier.
 *
 * A Server Component that awaits the fetch, matching /inventory/spoilage.
 * Reads only — nothing here writes or proposes until a bundle's own button
 * is pressed, which is a Server Action, not this render.
 */
export default async function PurchasingPage() {
  const { data, error } = await api.GET("/purchasing/reorder-suggestions", {});

  if (error) {
    return (
      <ApiErrorState title="Couldn't load reorder suggestions" detail={error.detail} />
    );
  }

  const { bundles, unsourced } = data;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <div className="mb-section flex shrink-0 items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Purchasing</h1>
          <p className="text-sm text-muted-foreground">
            Low stock, grouped by supplier and priced against each one&apos;s
            minimum order.
          </p>
        </div>
        <Link
          href="/purchasing/orders"
          className="flex h-control items-center rounded-(--radius) border border-border bg-card px-4 text-sm text-foreground"
        >
          View orders
        </Link>
      </div>

      {bundles.length === 0 && unsourced.length === 0 && (
        <div className="rounded-(--radius) border border-dashed border-border p-16 text-center">
          <div className="text-sm font-semibold">Nothing to reorder</div>
          <div className="mt-1 text-sm text-muted-foreground">
            Every product is at or above its reorder level.
          </div>
        </div>
      )}

      {bundles.length > 0 && (
        <div className="mb-section grid grid-cols-1 gap-stack md:grid-cols-2">
          {bundles.map((bundle) => (
            <BundleCard key={bundle.supplier_id} bundle={bundle} />
          ))}
        </div>
      )}

      {/*
        Shown, not hidden. "3 low products no supplier stocks" is information
        a manager needs — the bundler cannot buy from nobody, and a shorter
        list here would look like the feature working when it is really a
        gap in the supplier catalogue.
      */}
      {unsourced.length > 0 && (
        <div className="shrink-0 rounded-(--radius) border border-dashed border-border p-4">
          <h2 className="mb-stack text-sm font-semibold">
            {unsourced.length} low product{unsourced.length === 1 ? "" : "s"} no
            supplier stocks
          </h2>
          <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
            {unsourced.map((item) => (
              <li key={item.product_id} className="flex justify-between">
                <span>
                  {item.name} <span className="font-mono text-xs">{item.sku}</span>
                </span>
                <span data-numeric className="font-mono">
                  {item.quantity_on_hand} on hand · reorder at {item.reorder_level}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
