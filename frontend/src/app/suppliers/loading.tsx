/** Skeleton at roughly the real height, so the page does not jump. */
export default function SuppliersLoading() {
  return (
    <div>
      <div className="mb-section h-6 w-36 animate-pulse rounded bg-muted" />
      <div className="mb-section h-48 w-full animate-pulse rounded-(--radius) bg-muted" />
      <div className="h-40 w-full max-w-md animate-pulse rounded-(--radius) bg-muted" />
    </div>
  );
}
