import Link from "next/link";

/**
 * Two distinct empty states — do not merge them. An empty catalogue and a
 * search that missed are different facts about the world and need
 * different calls to action. See the screen inventory in
 * docs/FRONTEND-PLAN.md.
 */

export function EmptyCatalogue() {
  return (
    <div className="flex flex-col items-center justify-center gap-stack rounded-(--radius) border border-dashed border-border p-16 text-center">
      <div className="text-sm font-semibold">No products yet</div>
      <div className="max-w-sm text-sm text-muted-foreground">
        The catalogue is empty. Add your first product to start tracking stock.
      </div>
      <Link
        href="/products/new"
        className="mt-1 h-control flex items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground"
      >
        Add your first product
      </Link>
    </div>
  );
}

export function NoResults({ search }: { search: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-stack rounded-(--radius) border border-dashed border-border p-16 text-center">
      <div className="text-sm font-semibold">No matches for &ldquo;{search}&rdquo;</div>
      <div className="max-w-sm text-sm text-muted-foreground">
        Nothing in the catalogue matches that search.
      </div>
      <Link
        href="/products"
        className="mt-1 h-control flex items-center rounded-(--radius) border border-border bg-card px-4 text-sm text-foreground"
      >
        Clear search
      </Link>
    </div>
  );
}
