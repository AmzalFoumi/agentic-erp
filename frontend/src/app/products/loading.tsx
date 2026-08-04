/**
 * Next's file-convention loading state — shown automatically while
 * page.tsx's async work is in flight. Skeleton rows at the real row
 * height (h-row) so the page doesn't jump when data lands.
 */
export default function ProductsLoading() {
  const rows = Array.from({ length: 6 });

  return (
    <div>
      <div className="mb-section h-6 w-24 animate-pulse rounded bg-muted" />
      <div className="overflow-hidden rounded-(--radius) border border-border">
        {rows.map((_, i) => (
          <div
            key={i}
            className="h-row flex items-center gap-4 border-t border-border px-cell-x first:border-t-0"
          >
            <div className="h-3 w-20 animate-pulse rounded bg-muted" />
            <div className="h-3 w-40 animate-pulse rounded bg-muted" />
            <div className="h-3 w-20 animate-pulse rounded bg-muted" />
            <div className="flex-1" />
            <div className="h-3 w-16 animate-pulse rounded bg-muted" />
            <div className="h-3 w-12 animate-pulse rounded bg-muted" />
          </div>
        ))}
      </div>
    </div>
  );
}
