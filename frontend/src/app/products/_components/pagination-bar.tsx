import Link from "next/link";

import { cn } from "@/lib/utils";

function pageHref(page: number, search: string | undefined) {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (page > 1) params.set("page", String(page));
  const qs = params.toString();
  return qs ? `/products?${qs}` : "/products";
}

export function PaginationBar({
  page,
  limit,
  total,
  search,
}: {
  page: number;
  limit: number;
  total: number;
  search?: string;
}) {
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const from = total === 0 ? 0 : (page - 1) * limit + 1;
  const to = Math.min(page * limit, total);

  const linkClass = (disabled: boolean) =>
    cn(
      "h-control flex items-center rounded-(--radius) border border-border px-3 text-sm",
      disabled
        ? "pointer-events-none text-muted-foreground opacity-50"
        : "bg-card text-foreground hover:bg-secondary",
    );

  return (
    <div className="mt-stack flex items-center justify-between text-sm text-muted-foreground">
      <span>
        {from}–{to} of {total} products
      </span>
      <div className="flex gap-1">
        <Link
          href={pageHref(page - 1, search)}
          aria-disabled={page <= 1}
          className={linkClass(page <= 1)}
        >
          Prev
        </Link>
        <span className="flex h-control items-center px-3 text-sm text-foreground">
          Page {page} of {totalPages}
        </span>
        <Link
          href={pageHref(page + 1, search)}
          aria-disabled={page >= totalPages}
          className={linkClass(page >= totalPages)}
        >
          Next
        </Link>
      </div>
    </div>
  );
}
