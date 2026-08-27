/**
 * Approximate placeholder for the supplier list. It cannot hold the exact
 * final height - that varies with how many suppliers come back - so it only
 * reduces the jump, it does not remove it.
 */
export default function SuppliersLoading() {
  return (
    <div>
      <div className="mb-section h-6 w-36 animate-pulse rounded bg-muted" />
      <div className="mb-section h-48 w-full animate-pulse rounded-(--radius) bg-muted" />
      <div className="h-40 w-full max-w-md animate-pulse rounded-(--radius) bg-muted" />
    </div>
  );
}
