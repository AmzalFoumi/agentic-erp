import type { components } from "@/lib/api/client";

type ErrorResponse = components["schemas"]["ErrorResponse"];

export type FormActionState = {
  fieldErrors: Record<string, string>;
  formError: string | null;
};

export const emptyFormState: FormActionState = { fieldErrors: {}, formError: null };

/**
 * Maps the backend's ten-value error union onto form UI, per the error-state
 * table in docs/FRONTEND-PLAN.md. `DuplicateError` and `RequestValidationError`
 * are field-level (rendered under the input); everything else is form-level
 * (rendered near the submit button).
 */
export function mapApiError(error: ErrorResponse): FormActionState {
  if (error.error === "DuplicateError") {
    // The only unique constraint today is sku, so anchoring here is safe —
    // revisit if a second unique field is ever added.
    return { fieldErrors: { sku: error.detail }, formError: null };
  }
  if (error.error === "RequestValidationError" && error.fields) {
    return { fieldErrors: error.fields, formError: null };
  }
  return { fieldErrors: {}, formError: error.detail };
}
