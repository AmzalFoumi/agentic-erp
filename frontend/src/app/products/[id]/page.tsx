import Link from "next/link";

import { ApiErrorState } from "@/components/domain/api-error-state";
import { MoneyDisplay } from "@/components/domain/money-display";
import { StockBadge } from "@/components/domain/stock-badge";
import { api } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

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

export default async function ProductDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
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
            href={`/products/${product.id}/adjust-stock`}
            className="flex h-control items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground"
          >
            Adjust stock
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-section gap-y-stack rounded-(--radius) border border-border bg-card p-section">
        <Field label="Category">{product.category ?? "—"}</Field>
        <Field label="Unit">{product.unit}</Field>
        <Field label="Cost price">
          <MoneyDisplay value={product.cost_price} />
        </Field>
        <Field label="Sell price">
          <MoneyDisplay value={product.sell_price} />
        </Field>
        <Field label="Quantity on hand">
          <span data-numeric className="font-mono">
            {product.quantity_on_hand}
          </span>
        </Field>
        <Field label="Reorder level">
          <span data-numeric className="font-mono">
            {product.reorder_level}
          </span>
        </Field>
        <Field label="Status">
          <StockBadge
            quantity_on_hand={product.quantity_on_hand}
            needs_reorder={product.needs_reorder}
          />
        </Field>
        <div />
        <Field label="Created">
          {formatDateTime(product.created_at)} · {product.created_by ?? "system"}
        </Field>
        <Field label="Updated">
          {formatDateTime(product.updated_at)} · {product.updated_by ?? "system"}
        </Field>
      </div>
    </div>
  );
}
