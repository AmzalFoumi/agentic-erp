"use server";

import { redirect } from "next/navigation";

import { api } from "@/lib/api/client";
import { mapApiError, type FormActionState } from "@/lib/api-error";

export async function receiveLot(
  id: number,
  _prevState: FormActionState,
  formData: FormData,
): Promise<FormActionState> {
  const lot_code = String(formData.get("lot_code") ?? "").trim();
  const quantity = Number(formData.get("quantity"));
  const expiryRaw = String(formData.get("expiry_date") ?? "").trim();
  const costRaw = String(formData.get("cost_price") ?? "").trim();
  const sellRaw = String(formData.get("sell_price") ?? "").trim();

  // `cost_price` crosses the wire as a string — the money convention, so the
  // exact cents the user typed reach the backend untouched by float parsing.
  // Empty optional fields are left off the body entirely, not sent as "".
  const { error } = await api.POST("/inventory/products/{product_id}/lots", {
    params: { path: { product_id: id } },
    body: {
      lot_code,
      quantity,
      ...(expiryRaw ? { expiry_date: expiryRaw } : {}),
      ...(costRaw ? { cost_price: costRaw } : {}),
      ...(sellRaw ? { sell_price: sellRaw } : {}),
    },
  });

  if (error) {
    return mapApiError(error);
  }

  redirect(`/products/${id}`);
}
