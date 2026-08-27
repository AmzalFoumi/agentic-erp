/**
 * Skeleton cards at roughly the real card height, so the page does not jump
 * when the queue lands.
 */
export default function ApprovalsLoading() {
  return (
    <div>
      <div className="mb-section h-6 w-28 animate-pulse rounded bg-muted" />
      <div className="flex flex-col gap-stack">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="rounded-(--radius) border border-border bg-card p-4"
          >
            <div className="mb-stack h-4 w-48 animate-pulse rounded bg-muted" />
            <div className="mb-stack h-3 w-full animate-pulse rounded bg-muted" />
            <div className="mb-stack h-3 w-2/3 animate-pulse rounded bg-muted" />
            <div className="flex gap-2">
              <div className="h-control w-36 animate-pulse rounded bg-muted" />
              <div className="h-control w-20 animate-pulse rounded bg-muted" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
