"use client";

import { ApiErrorState } from "@/components/domain/api-error-state";

/**
 * "We could not find out" — distinct from "nothing is expiring" on purpose.
 * Confusing the two would tell a manager the shelves are fine when the truth
 * is that nobody looked.
 *
 * The wording is failure-NEUTRAL, and that is a correction rather than a
 * style choice. This boundary catches anything thrown while rendering the
 * segment, not only a fetch that failed — so naming the backend as the cause
 * would be a guess presented as a diagnosis, and would send someone to check a
 * server that is running perfectly well.
 */
export default function SpoilageError({ reset }: { reset: () => void }) {
  return (
    <ApiErrorState
      title="Couldn't load the spoilage report"
      detail="We could not load the spoilage report. This isn't an all-clear — nothing was checked, so stock may still be expiring. Retry the request."
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
