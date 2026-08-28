import { ApiErrorState } from "@/components/domain/api-error-state";
import { api } from "@/lib/api/client";

import { createSupplier } from "./actions";
import { SupplierForm } from "./_components/supplier-form";
import { SupplierTable } from "./_components/supplier-table";

/**
 * Every supplier, active and inactive, with a create form.
 *
 * A Server Component that awaits the fetch, matching /products and
 * /approvals. No pagination: five to a few dozen suppliers is the realistic
 * ceiling for a single shop, unlike the product catalogue.
 */
export default async function SuppliersPage() {
  const { data, error } = await api.GET("/suppliers", {});

  if (error) {
    return <ApiErrorState title="Couldn't load suppliers" detail={error.detail} />;
  }

  const { items } = data;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-section shrink-0">
        <h1 className="text-lg font-semibold">Suppliers</h1>
        <p className="text-sm text-muted-foreground">
          Who the shop buys from. There is no delete here — a supplier that
          stops being used is deactivated instead, so past orders keep a name
          rather than pointing at nothing.
        </p>
      </div>

      {items.length === 0 ? (
        <div className="mb-section rounded-(--radius) border border-dashed border-border p-16 text-center">
          <div className="text-sm font-semibold">No suppliers yet</div>
          <div className="mt-1 text-sm text-muted-foreground">
            Add one below to start building a price list.
          </div>
        </div>
      ) : (
        <div className="mb-section">
          <SupplierTable suppliers={items} />
        </div>
      )}

      <div className="shrink-0 rounded-(--radius) border border-border bg-card p-section">
        <h2 className="mb-stack text-sm font-semibold">Add a supplier</h2>
        <SupplierForm
          action={createSupplier}
          submitLabel="Add supplier"
          submitPendingLabel="Adding…"
        />
      </div>
    </div>
  );
}
