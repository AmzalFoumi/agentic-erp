import { ApiErrorState } from "@/components/domain/api-error-state";
import { api } from "@/lib/api/client";

import { EmptyCatalogue, NoResults } from "./_components/empty-states";
import { PaginationBar } from "./_components/pagination-bar";
import { ProductsTable } from "./_components/products-table";

const LIMIT = 50;

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string; page?: string }>;
}) {
  const { search, page: pageParam } = await searchParams;
  const page = Math.max(1, Number(pageParam) || 1);
  const offset = (page - 1) * LIMIT;

  // A thrown network failure (no response at all) is not caught here —
  // it propagates to error.tsx, which is the "backend unreachable" state.
  // Only a real ErrorResponse from the API is handled inline.
  const { data, error } = await api.GET("/products", {
    params: {
      query: { search: search || undefined, limit: LIMIT, offset },
    },
  });

  if (error) {
    return (
      <ApiErrorState
        title="Couldn't load products"
        detail={error.detail}
      />
    );
  }

  const { items, total } = data;
  const hasSearch = Boolean(search);
  const isEmptyCatalogue = total === 0 && !hasSearch;
  const isNoResults = total === 0 && hasSearch;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-section flex shrink-0 items-center justify-between">
        <h1 className="text-lg font-semibold">Products</h1>
        {!isEmptyCatalogue && (
          <form action="/products" className="flex">
            <input
              type="text"
              name="search"
              defaultValue={search}
              placeholder="Search name or SKU"
              className="h-control w-64 rounded-(--radius) border border-input bg-card px-3 text-sm text-foreground"
            />
          </form>
        )}
      </div>

      {isEmptyCatalogue && <EmptyCatalogue />}
      {isNoResults && <NoResults search={search!} />}
      {!isEmptyCatalogue && !isNoResults && (
        <>
          <ProductsTable products={items} />
          <div className="shrink-0">
            <PaginationBar page={page} limit={LIMIT} total={total} search={search} />
          </div>
        </>
      )}
    </div>
  );
}
