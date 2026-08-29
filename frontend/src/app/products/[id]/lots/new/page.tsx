import Link from "next/link";

import { ApiErrorState } from "@/components/domain/api-error-state";
import { api } from "@/lib/api/client";

import { ReceiveLotForm } from "./_components/receive-lot-form";

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

export default async function AddLotPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: idParam } = await params;
  const id = Number(idParam);

  if (!Number.isInteger(id)) {
    return (
      <ApiErrorState
        title="Product not found"
        detail="That link doesn't point to a real product."
        action={<BackToList />}
      />
    );
  }

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
    <div>
      <h1 className="mb-1 text-lg font-semibold">Add lot</h1>
      <div className="mb-section text-sm text-muted-foreground">
        {product.name} · {product.sku}
      </div>
      <ReceiveLotForm id={product.id} />
    </div>
  );
}
