"use server";

/**
 * Staging a markdown proposal from the website.
 *
 * A Server Action rather than a route under `app/api`, for the reason in
 * `docs/FRONTEND-PLAN.md`: a Next route handler that proxies to FastAPI is a
 * *third adapter*, the same category of mistake as `services/` importing
 * `api/`.
 *
 * ⚠️ Note what this file does NOT send: no prices, no lot ids, no discount
 * percentages. It asks the backend to propose something, and the backend
 * scans, prices and stages. If the browser sent the lines, the discount ladder
 * would exist in two places and would eventually disagree with itself — the
 * shop advertising one price and the till charging another.
 */

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api/client";

export type ProposeResult = { error: string } | { draftId: number };

/**
 * Stage the current spoilage as one draft for a human to approve.
 *
 * Nothing is discounted by calling this. The proposal lands in /approvals and
 * a person — not this action, and not the assistant — decides.
 */
export async function proposeMarkdown(): Promise<ProposeResult> {
  const { data, error } = await api.POST("/inventory/spoilage/propose", {
    body: { within_days: null, reasoning: null },
  });

  if (error) {
    return { error: error.detail };
  }

  // Both pages change: the queue gains a proposal, and the spoilage screen
  // should show that one is now pending rather than inviting a second.
  revalidatePath("/approvals");
  revalidatePath("/inventory/spoilage");
  return { draftId: data.id };
}
