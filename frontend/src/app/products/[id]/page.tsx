import Link from "next/link";

import { ApiErrorState } from "@/components/domain/api-error-state";
import { ExpiryBadge } from "@/components/domain/expiry-badge";
import { MoneyDisplay } from "@/components/domain/money-display";
import { StockBadge } from "@/components/domain/stock-badge";
import { api } from "@/lib/api/client";
import { formatDateTime, priceRange } from "@/lib/format";

function BackToList() {
  return (
    <Link
      href="/products"
      className="mt-1 flex h-control items-center rounded-(--radius) border border-border bg-card px-4 text-sm text-foreground"
    >
      Back to products
    </Link>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-xs text-muted-foreground">{label}</div>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function Tile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-(--radius) border border-border bg-card p-4">
      <div className="mb-1 text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold">{children}</div>
    </div>
  );
}

export default async function ProductDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: idParam } = await params;
  const id = Number(idParam);

  // Not a number at all — an /products/abc link. Same treatment as a 404:
  // full-page state, a way back, no call to an API that would just 404 too.
  if (!Number.isInteger(id)) {
    return (
      <ApiErrorState
        title="Product not found"
        detail="That link doesn't point to a real product."
        action={<BackToList />}
      />
    );
  }

  // A thrown network failure propagates to error.tsx (backend-unreachable
  // state). Only a real ErrorResponse — including 404 — is handled here.
  const { data: product, error } = await api.GET("/products/{product_id}", {
    params: { path: { product_id: id } },
  });

  if (error) {
    return (
      <ApiErrorState
        title={error.error === "NotFoundError" ? "Product not found" : "Couldn't load product"}
        detail={error.detail}
        action={<BackToList />}
      />
    );
  }

  // The lots — deliberately a soft failure. If the signed-in user cannot read
  // lots (a 403), or the list is otherwise unavailable, the rest of the page
  // still renders; the Lots section shows a muted note instead of a lot table.
  const { data: lots, error: lotsError } = await api.GET("/inventory/products/{product_id}/lots", {
    params: { path: { product_id: id } },
  });

  const lotsUnavailable = Boolean(lotsError) && lotsError?.error !== "NotFoundError";

  return (
    <div className="max-w-2xl">
      <div className="mb-section flex items-baseline justify-between">
        <div>
          <div className="font-mono text-sm text-muted-foreground">{product.sku}</div>
          <h1 className="mt-1 text-lg font-semibold">{product.name}</h1>
        </div>
        <div className="flex gap-2">
          <Link
            href={`/products/${product.id}/edit`}
            className="flex h-control items-center rounded-(--radius) border border-border bg-card px-4 text-sm text-foreground"
          >
            Edit
          </Link>
          <Link
            href={`/products/${product.id}/lots/new`}
            className="flex h-control items-center rounded-(--radius) border border-border bg-card px-4 text-sm text-foreground"
          >
            Add lot
          </Link>
          {/* <Link
            href={`/products/${product.id}/adjust-stock`}
            className="flex h-control items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground"
          >
            Adjust stock
          </Link> */}
        </div>
      </div>

      <div className="mb-section grid grid-cols-2 gap-stack sm:grid-cols-4">
        <Tile label="Quantity on hand">
          <span className="font-mono tabular-nums">{product.quantity_on_hand}</span>
        </Tile>
        <Tile label="Lots">
          <span className="font-mono tabular-nums">{lots ? lots.total : "—"}</span>
        </Tile>
        <Tile label="Reorder level">
          <span className="font-mono tabular-nums">{product.reorder_level}</span>
        </Tile>
        <Tile label="Status">
          <StockBadge
            quantity_on_hand={product.quantity_on_hand}
            needs_reorder={product.needs_reorder}
          />
        </Tile>
      </div>

      <div className="mb-section grid grid-cols-2 gap-x-section gap-y-stack rounded-(--radius) border border-border bg-card p-section">
        <Field label="Category">{product.category ?? "—"}</Field>
        <Field label="Unit">{product.unit}</Field>
        <Field label="Cost price (catalogue)">
          <MoneyDisplay value={product.cost_price} />
          {product.min_cost_price !== null &&
          product.min_cost_price !== product.max_cost_price ? (
            <div className="text-xs text-muted-foreground">
              lots {priceRange(product.min_cost_price, product.max_cost_price, product.cost_price)}
            </div>
          ) : null}
        </Field>
        <Field label="Sell price (catalogue)">
          <MoneyDisplay value={product.sell_price} />
          {product.min_sell_price !== null &&
          product.min_sell_price !== product.max_sell_price ? (
            <div className="text-xs text-muted-foreground">
              lots {priceRange(product.min_sell_price, product.max_sell_price, product.sell_price)}
            </div>
          ) : null}
        </Field>
        <Field label="Created">
          {formatDateTime(product.created_at)} · {product.created_by ?? "system"}
        </Field>
        <Field label="Updated">
          {formatDateTime(product.updated_at)} · {product.updated_by ?? "system"}
        </Field>
      </div>

      <section className="rounded-(--radius) border border-border bg-card p-section">
        <div className="mb-stack flex items-baseline justify-between">
          <h2 className="text-sm font-semibold">Lots{lots ? ` · ${lots.total}` : ""}</h2>
          <Link
            href={`/products/${product.id}/lots/new`}
            className="text-sm text-primary hover:underline"
          >
            Add lot
          </Link>
        </div>

        {lotsUnavailable ? (
          <p className="text-sm text-muted-foreground">
            Lot history isn&apos;t available for your account.
          </p>
        ) : !lots || lots.items.length === 0 ? (
          <div className="rounded-(--radius) border border-dashed border-border p-section text-center text-sm text-muted-foreground">
            No lots recorded yet.{" "}
            <Link
              href={`/products/${product.id}/lots/new`}
              className="text-primary hover:underline"
            >
              Add the first one
            </Link>
            .
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">Lot</th>
                  <th className="py-2 pr-3 font-medium">Expiry</th>
                  <th className="py-2 pr-3 text-right font-medium">Quantity</th>
                  <th className="py-2 pr-3 text-right font-medium">Unit cost</th>
                  <th className="py-2 pr-3 text-right font-medium">Sell price</th>
                  <th className="py-2 font-medium">Received</th>
                </tr>
              </thead>
              <tbody>
                {lots.items.map((lot) => (
                  <tr key={lot.id} className="border-b border-border last:border-0">
                    <td className="py-2 pr-3 font-mono text-xs">{lot.lot_code}</td>
                    <td className="py-2 pr-3">
                      <ExpiryBadge expiryDate={lot.expiry_date} isExpired={lot.is_expired} />
                    </td>
                    <td className="py-2 pr-3 text-right font-mono tabular-nums">{lot.quantity}</td>
                    <td className="py-2 pr-3 text-right">
                      <MoneyDisplay value={lot.cost_price} />
                    </td>
                    <td className="py-2 pr-3 text-right">
                      <MoneyDisplay value={lot.sell_price} />
                      {lot.discount_percent > 0 ? (
                        <div className="text-xs text-muted-foreground">
                          −{lot.discount_percent}%
                        </div>
                      ) : null}
                    </td>
                    <td className="py-2 text-xs text-muted-foreground">
                      {formatDateTime(lot.created_at)} · {lot.created_via}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
