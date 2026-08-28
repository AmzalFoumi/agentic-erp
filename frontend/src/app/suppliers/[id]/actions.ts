"use server";

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api/client";
import type { FormActionState } from "@/lib/api-error";
import type { components } from "@/lib/api/client";

type ErrorResponse = components["schemas"]["ErrorResponse"];

function mapSupplierError(error: ErrorResponse): FormActionState {
  if (error.error === "DuplicateError") {
    return { fieldErrors: { name: error.detail }, formError: null };
  }
  if (error.error === "RequestValidationError" && error.fields) {
    return { fieldErrors: error.fields, formError: null };
  }
  return { fieldErrors: {}, formError: error.detail };
}

export async function updateSupplier(
  supplierId: number,
  _prevState: FormActionState,
  formData: FormData,
): Promise<FormActionState> {
  const contactEmail = String(formData.get("contact_email") ?? "").trim();
  const contactPhone = String(formData.get("contact_phone") ?? "").trim();

  const { error } = await api.PATCH("/suppliers/{supplier_id}", {
    params: { path: { supplier_id: supplierId } },
    body: {
      name: String(formData.get("name") ?? "").trim(),
      contact_email: contactEmail || null,
      contact_phone: contactPhone || null,
      lead_time_days: Number(formData.get("lead_time_days")) || 0,
      minimum_order_value:
        String(formData.get("minimum_order_value") ?? "").trim() || "0.00",
    },
  });

  if (error) {
    return mapSupplierError(error);
  }

  revalidatePath(`/suppliers/${supplierId}`);
  revalidatePath("/suppliers");
  return { fieldErrors: {}, formError: null };
}

export async function deactivateSupplier(
  supplierId: number,
): Promise<{ error: string } | null> {
  const { error } = await api.PATCH("/suppliers/{supplier_id}", {
    params: { path: { supplier_id: supplierId } },
    body: { is_active: false },
  });

  if (error) {
    return { error: error.detail };
  }

  revalidatePath(`/suppliers/${supplierId}`);
  revalidatePath("/suppliers");
  return null;
}

/**
 * Record that this supplier sells one more product, at a price.
 *
 * `fieldErrors` here key by product_id/unit_cost/pack_size, same convention
 * as everywhere else — DuplicateError means "already linked", which is a
 * product_id problem, not a name problem.
 */
export async function linkProduct(
  supplierId: number,
  _prevState: FormActionState,
  formData: FormData,
): Promise<FormActionState> {
  const productId = Number(formData.get("product_id"));

  const { error } = await api.POST("/suppliers/{supplier_id}/products", {
    params: { path: { supplier_id: supplierId } },
    body: {
      product_id: productId,
      unit_cost: String(formData.get("unit_cost") ?? "").trim() || "0.00",
      pack_size: Number(formData.get("pack_size")) || 1,
      is_preferred: formData.get("is_preferred") === "on",
    },
  });

  if (error) {
    if (error.error === "DuplicateError") {
      return { fieldErrors: { product_id: error.detail }, formError: null };
    }
    if (error.error === "RequestValidationError" && error.fields) {
      return { fieldErrors: error.fields, formError: null };
    }
    return { fieldErrors: {}, formError: error.detail };
  }

  revalidatePath(`/suppliers/${supplierId}`);
  return { fieldErrors: {}, formError: null };
}

/** Toggle which supplier link is preferred for a product. */
export async function setPreferred(
  supplierId: number,
  linkId: number,
  isPreferred: boolean,
): Promise<{ error: string } | null> {
  const { error } = await api.PATCH("/supplier-products/{link_id}", {
    params: { path: { link_id: linkId } },
    body: { is_preferred: isPreferred },
  });

  if (error) {
    return { error: error.detail };
  }

  revalidatePath(`/suppliers/${supplierId}`);
  return null;
}
