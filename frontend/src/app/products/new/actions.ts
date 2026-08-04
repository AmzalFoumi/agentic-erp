"use server";

import { redirect } from "next/navigation";

import { api } from "@/lib/api/client";
import { mapApiError, type FormActionState } from "@/lib/api-error";

export async function createProduct(
  _prevState: FormActionState,
  formData: FormData,
): Promise<FormActionState> {
  const category = String(formData.get("category") ?? "").trim();

  const { data, error } = await api.POST("/products", {
    body: {
      sku: String(formData.get("sku") ?? "").trim(),
      name: String(formData.get("name") ?? "").trim(),
      category: category || null,
      unit: String(formData.get("unit") ?? "").trim() || "piece",
      // Sent as a string, deliberately — see the money-as-string rule in
      // DESIGN.md. Never Number()/parseFloat a price on its way to the API.
      cost_price: String(formData.get("cost_price") ?? "").trim() || "0.00",
      sell_price: String(formData.get("sell_price") ?? "").trim() || "0.00",
      quantity_on_hand: Number(formData.get("quantity_on_hand")) || 0,
      reorder_level: Number(formData.get("reorder_level")) || 0,
    },
  });

  if (error) {
    return mapApiError(error);
  }

  redirect(`/products/${data.id}`);
}
