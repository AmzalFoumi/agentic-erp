"use client";

import { ApiErrorState } from "@/components/domain/api-error-state";

/**
 * Failure-neutral wording, same reasoning as every other error.tsx in this
 * app: this boundary catches anything thrown while rendering the segment,
 * not only a fetch that failed, so naming a cause would be a guess.
 */
export default function PurchasingError({ reset }: { reset: () => void }) {
  return (
    <ApiErrorState
      title="Couldn't load reorder suggestions"
      detail="We could not work out what needs reordering. This isn't an all-clear — nothing was checked. Retry the request."
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
