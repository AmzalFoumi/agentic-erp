"use client";

import { ApiErrorState } from "@/components/domain/api-error-state";

/**
 * "We could not find out" — distinct from "nothing is expiring" on purpose.
 * Confusing the two would tell a manager the shelves are fine when the truth
 * is that nobody looked.
 */
export default function SpoilageError({ reset }: { reset: () => void }) {
  return (
    <ApiErrorState
      title="Couldn't reach the server"
      detail="The backend didn't respond. This isn't an all-clear — nothing was checked, so stock may still be expiring."
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
