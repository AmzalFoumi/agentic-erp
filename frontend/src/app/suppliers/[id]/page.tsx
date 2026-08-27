import Link from "next/link";

import { ApiErrorState } from "@/components/domain/api-error-state";
import { api } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

import { linkProduct, updateSupplier } from "./actions";
import { DeactivateAction } from "./_components/deactivate-action";
import { LinkForm } from "./_components/link-form";
import { LinksTable } from "./_components/links-table";
import { SupplierForm } from "../_components/supplier-form";

function BackToList() {
  return (
    <Link
      href="/suppliers"
      className="mt-1 flex h-control items-center rounded-(--radius) border border-border bg-card px-4 text-sm text-foreground"
    >
      Back to suppliers
    </Link>
  );
}

export default async function SupplierDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: idParam } = await params;
  const id = Number(idParam);

  if (!Number.isInteger(id)) {
    return (
      <ApiErrorState
        title="Supplier not found"
        detail="That link doesn't point to a real supplier."
        action={<BackToList />}
      />
    );
  }

  const [{ data: supplier, error: supplierError }, linksResult, productsResult] =
    await Promise.all([
      api.GET("/suppliers/{supplier_id}", { params: { path: { supplier_id: id } } }),
      api.GET("/suppliers/{supplier_id}/products", {
        params: { path: { supplier_id: id } },
      }),
      // The whole catalogue, so the link form and links table can show
      // names rather than bare ids without a round trip per row. 200 is the
      // API's own ceiling on this endpoint and comfortably covers a demo
      // catalogue.
      api.GET("/products", { params: { query: { limit: 200, offset: 0 } } }),
    ]);

  if (supplierError) {
    return (
      <ApiErrorState
        title={supplierError.error === "NotFoundError" ? "Supplier not found" : "Couldn't load supplier"}
        detail={supplierError.detail}
        action={<BackToList />}
      />
    );
  }

  if (linksResult.error) {
    return (
      <ApiErrorState
        title="Couldn't load this supplier's price list"
        detail={linksResult.error.detail}
        action={<BackToList />}
      />
    );
  }

  if (productsResult.error) {
    return (
      <ApiErrorState
        title="Couldn't load the product catalogue"
        detail={productsResult.error.detail}
        action={<BackToList />}
      />
    );
  }

  const links = linksResult.data.items;
  const products = productsResult.data.items;
  const boundUpdate = updateSupplier.bind(null, supplier.id);
  const boundLink = linkProduct.bind(null, supplier.id);

  return (
    <div className="max-w-2xl">
      <div className="mb-section flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold">{supplier.name}</h1>
          <p className="text-sm text-muted-foreground">
            {supplier.is_active ? "Active" : "Inactive"} · added{" "}
            {formatDateTime(supplier.created_at)}
          </p>
        </div>
        {supplier.is_active && <DeactivateAction supplierId={supplier.id} />}
      </div>

      <div className="mb-section rounded-(--radius) border border-border bg-card p-section">
        <h2 className="mb-stack text-sm font-semibold">Details</h2>
        <SupplierForm
          action={boundUpdate}
          supplier={supplier}
          submitLabel="Save changes"
          submitPendingLabel="Saving…"
        />
      </div>

      <div className="mb-section">
        <h2 className="mb-stack text-sm font-semibold">Price list</h2>
        {links.length === 0 ? (
          <div className="rounded-(--radius) border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            No products linked yet.
          </div>
        ) : (
          <LinksTable supplierId={supplier.id} links={links} products={products} />
        )}
      </div>

      <div className="rounded-(--radius) border border-border bg-card p-section">
        <h2 className="mb-stack text-sm font-semibold">Add to price list</h2>
        <LinkForm action={boundLink} products={products} />
      </div>
    </div>
  );
}
