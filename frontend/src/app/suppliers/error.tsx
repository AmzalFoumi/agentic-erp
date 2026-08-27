"use client";

import { ApiErrorState } from "@/components/domain/api-error-state";

/**
 * Failure-neutral wording, same reasoning as inventory/spoilage/error.tsx:
 * this boundary catches anything thrown while rendering the segment, not
 * only a fetch that failed, so naming a cause would be a guess.
 */
export default function SuppliersError({ reset }: { reset: () => void }) {
  return (
    <ApiErrorState
      title="Couldn't load suppliers"
      detail="We could not load the supplier list. Retry the request."
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
