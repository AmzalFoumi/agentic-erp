/** Skeleton at roughly the real height, so the page does not jump. */
export default function SpoilageLoading() {
  return (
    <div>
      <div className="mb-section h-6 w-36 animate-pulse rounded bg-muted" />
      <div className="mb-section flex gap-8">
        <div className="h-10 w-32 animate-pulse rounded bg-muted" />
        <div className="h-10 w-32 animate-pulse rounded bg-muted" />
      </div>
      <div className="h-64 w-full animate-pulse rounded-(--radius) bg-muted" />
    </div>
  );
}
