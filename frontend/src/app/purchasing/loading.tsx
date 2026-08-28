/** Skeleton at roughly the real height, so the page does not jump. */
export default function PurchasingLoading() {
  return (
    <div>
      <div className="mb-section h-6 w-36 animate-pulse rounded bg-muted" />
      <div className="grid grid-cols-1 gap-stack md:grid-cols-2">
        <div className="h-48 w-full animate-pulse rounded-(--radius) bg-muted" />
        <div className="h-48 w-full animate-pulse rounded-(--radius) bg-muted" />
      </div>
    </div>
  );
}
