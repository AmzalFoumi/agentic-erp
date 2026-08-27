"use server";

/**
 * Staging one supplier's reorder bundle as a draft for a human to approve.
 *
 * Same shape as inventory/spoilage/actions.ts: a Server Action rather than a
 * route under `app/api` (that would be a third adapter), and it sends only
 * the supplier id and the reasoning — never the lines, the quantities, or the
 * prices. The server re-scans and re-prices at proposal time; a browser that
 * sent the lines would be doing business logic, and two clients would
 * eventually disagree about what a supplier's bundle actually costs.
 */

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api/client";

export type ProposeResult = { error: string } | { draftId: number };

export async function proposeReorder(
  supplierId: number,
  reasoning: string,
): Promise<ProposeResult> {
  const { data, error } = await api.POST("/purchasing/reorder-drafts", {
    body: { supplier_id: supplierId, reasoning: reasoning || null },
  });

  if (error) {
    return { error: error.detail };
  }

  revalidatePath("/approvals");
  revalidatePath("/purchasing");
  return { draftId: data.id };
}
