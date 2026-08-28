"use server";

/**
 * The two decisions a manager can make about a proposal.
 *
 * Server Actions rather than a route under `app/api`, for the reason set out
 * in `docs/FRONTEND-PLAN.md`: a Next route handler that proxies to FastAPI is
 * a *third adapter*, the same category of mistake as `services/` importing
 * `api/`. These are plain functions the form posts to, running on the server
 * so they can use the `server-only` typed client.
 *
 * Neither of these decides anything itself. Both forward to the backend, which
 * checks `draft.decide`, re-validates the payload against the draft type's own
 * schema, and runs the handler. Nothing here is trusted — this file carries an
 * intent, it does not authorise one.
 */

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api/client";

/**
 * What a decision returns to the page: nothing on success, a message on
 * failure.
 *
 * `null` for success rather than a boolean, so a caller cannot write
 * `if (result)` and get it backwards.
 */
export type DecisionResult = { error: string } | null;

/**
 * Approve a proposal, optionally with the manager's edits, and run it.
 *
 * `payload` is only sent when the manager actually changed something. Sending
 * an unchanged copy would work, but it would make every approval look like an
 * edit in the audit trail, which is exactly the distinction the queue exists
 * to record.
 */
export async function approveDraft(
  draftId: number,
  payload?: Record<string, unknown>,
): Promise<DecisionResult> {
  const { error } = await api.POST("/drafts/{draft_id}/approve", {
    params: { path: { draft_id: draftId } },
    body: { payload: payload ?? null },
  });

  if (error) {
    return { error: error.detail };
  }

  // The queue is a list of things that are about to stop being pending, so the
  // page must not be served from cache after one is decided. `revalidatePath`
  // rather than `redirect`: the manager is usually working through several
  // proposals and should stay where they are.
  revalidatePath("/approvals");
  return null;
}

/** Reject a proposal. Terminal, and runs nothing. */
export async function rejectDraft(draftId: number): Promise<DecisionResult> {
  const { error } = await api.POST("/drafts/{draft_id}/reject", {
    params: { path: { draft_id: draftId } },
  });

  if (error) {
    return { error: error.detail };
  }

  revalidatePath("/approvals");
  return null;
}
