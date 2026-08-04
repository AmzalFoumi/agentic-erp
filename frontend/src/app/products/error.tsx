"use client";

import { ApiErrorState } from "@/components/domain/api-error-state";

/**
 * The "backend unreachable" row of the error-state table: no response at
 * all, not a parseable ErrorResponse. Next's error boundary is the right
 * mechanism for this — a thrown fetch failure in page.tsx lands here
 * automatically, and `reset()` re-runs the Server Component rather than a
 * full page reload. Never render an empty list for this case.
 */
export default function ProductsError({ reset }: { reset: () => void }) {
  return (
    <ApiErrorState
      title="Couldn't reach the server"
      detail="The backend didn't respond. This isn't an empty catalogue — nothing was loaded."
      action={
        <button
          type="button"
          onClick={() => reset()}
          className="mt-1 h-control flex items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground"
        >
          Retry
        </button>
      }
    />
  );
}
