"use server";

/**
 * Server Actions for the supplier list: create and deactivate.
 *
 * Server Actions rather than a route under `app/api`, for the reason set out
 * in `docs/FRONTEND-PLAN.md`: a Next route handler that proxies to FastAPI is
 * a *third adapter*, the same category of mistake as `services/` importing
 * `api/`.
 */

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api/client";
import type { FormActionState } from "@/lib/api-error";
import type { components } from "@/lib/api/client";

type ErrorResponse = components["schemas"]["ErrorResponse"];

/**
 * Same shape as `mapApiError` in `@/lib/api-error`, but anchored on `name`
 * rather than `sku` — suppliers' only unique constraint is their name, and
 * `mapApiError` hardcodes the product-catalogue's field on purpose.
 */
function mapSupplierError(error: ErrorResponse): FormActionState {
  if (error.error === "DuplicateError") {
    return { fieldErrors: { name: error.detail }, formError: null };
  }
  if (error.error === "RequestValidationError" && error.fields) {
    return { fieldErrors: error.fields, formError: null };
  }
  return { fieldErrors: {}, formError: error.detail };
}

export async function createSupplier(
  _prevState: FormActionState,
  formData: FormData,
): Promise<FormActionState> {
  const contactEmail = String(formData.get("contact_email") ?? "").trim();
  const contactPhone = String(formData.get("contact_phone") ?? "").trim();

  const { error } = await api.POST("/suppliers", {
    body: {
      name: String(formData.get("name") ?? "").trim(),
      contact_email: contactEmail || null,
      contact_phone: contactPhone || null,
      lead_time_days: Number(formData.get("lead_time_days")) || 0,
      // Sent as a string, deliberately — see the money-as-string rule in
      // DESIGN.md. Never Number()/parseFloat a money value on its way out.
      minimum_order_value:
        String(formData.get("minimum_order_value") ?? "").trim() || "0.00",
    },
  });

  if (error) {
    return mapSupplierError(error);
  }

  revalidatePath("/suppliers");
  return { fieldErrors: {}, formError: null };
}

/**
 * There is no delete anywhere in this API. `is_active = false` is how a
 * supplier leaves, so order history keeps a name rather than an orphaned id.
 */
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

  revalidatePath("/suppliers");
  return null;
}
