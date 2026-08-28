"use client";

import { ApiErrorState } from "@/components/domain/api-error-state";

/**
 * The "backend unreachable" state: no response at all, not a parseable
 * ErrorResponse. Distinct from an empty queue on purpose — "nothing to
 * approve" and "we could not find out" must never look the same, because the
 * first one invites the manager to go home.
 */
export default function ApprovalsError({ reset }: { reset: () => void }) {
  return (
    <ApiErrorState
      title="Couldn't reach the server"
      detail="The backend didn't respond. This isn't an empty queue — nothing was loaded, so there may be proposals waiting."
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
