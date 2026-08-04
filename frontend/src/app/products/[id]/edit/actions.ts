"use server";

import { redirect } from "next/navigation";

import { api } from "@/lib/api/client";
import { mapApiError, type FormActionState } from "@/lib/api-error";

export async function updateProduct(
  id: number,
  _prevState: FormActionState,
  formData: FormData,
): Promise<FormActionState> {
  const category = String(formData.get("category") ?? "").trim();

  const { error } = await api.PATCH("/products/{product_id}", {
    params: { path: { product_id: id } },
    body: {
      name: String(formData.get("name") ?? "").trim(),
      category: category || null,
      unit: String(formData.get("unit") ?? "").trim(),
      cost_price: String(formData.get("cost_price") ?? "").trim(),
      sell_price: String(formData.get("sell_price") ?? "").trim(),
      reorder_level: Number(formData.get("reorder_level")) || 0,
    },
  });

  if (error) {
    return mapApiError(error);
  }

  redirect(`/products/${id}`);
}
