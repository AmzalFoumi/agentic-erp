"use server";

import { redirect } from "next/navigation";

import { api } from "@/lib/api/client";
import { mapApiError, type FormActionState } from "@/lib/api-error";

export async function adjustStock(
  id: number,
  _prevState: FormActionState,
  formData: FormData,
): Promise<FormActionState> {
  const delta = Number(formData.get("delta"));

  // No `reason` field in the body — the capability inventory is explicit
  // that the backend accepts and discards it, so the form must not offer
  // an input whose value goes nowhere. See docs/FRONTEND-PLAN.md.
  const { error } = await api.POST("/products/{product_id}/adjust-stock", {
    params: { path: { product_id: id } },
    body: { delta },
  });

  if (error) {
    return mapApiError(error);
  }

  redirect(`/products/${id}`);
}
