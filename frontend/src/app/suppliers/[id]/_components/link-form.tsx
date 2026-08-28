"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { FIELD_CLASS, FieldError, FormError } from "@/components/domain/form-field";
import { emptyFormState, type FormActionState } from "@/lib/api-error";
import type { components } from "@/lib/api/client";

type Product = components["schemas"]["ProductRead"];

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="flex h-control items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
    >
      {pending ? "Adding…" : "Add to price list"}
    </button>
  );
}

/**
 * Add one product to this supplier's price list.
 *
 * `products` is the whole catalogue, fetched once by the server page. A
 * `<select>` rather than a bare id input, so a manager picks a product by
 * name instead of typing an id they have to look up first.
 */
export function LinkForm({
  action,
  products,
}: {
  action: (state: FormActionState, formData: FormData) => Promise<FormActionState>;
  products: Product[];
}) {
  const [state, formAction] = useActionState(action, emptyFormState);

  return (
    <form action={formAction} className="flex flex-col gap-stack">
      <div>
        <label htmlFor="product_id" className="mb-1 block text-xs text-muted-foreground">
          Product
        </label>
        <select
          id="product_id"
          name="product_id"
          required
          defaultValue=""
          aria-invalid={Boolean(state.fieldErrors.product_id)}
          className={FIELD_CLASS}
        >
          <option value="" disabled>
            Choose a product
          </option>
          {products.map((product) => (
            <option key={product.id} value={product.id}>
              {product.sku} — {product.name}
            </option>
          ))}
        </select>
        <FieldError message={state.fieldErrors.product_id} />
      </div>

      <div className="grid grid-cols-3 gap-stack">
        <div>
          <label htmlFor="unit_cost" className="mb-1 block text-xs text-muted-foreground">
            Unit cost (Rs)
          </label>
          <input
            id="unit_cost"
            name="unit_cost"
            inputMode="decimal"
            defaultValue="0.00"
            aria-invalid={Boolean(state.fieldErrors.unit_cost)}
            className={`${FIELD_CLASS} font-mono`}
          />
          <FieldError message={state.fieldErrors.unit_cost} />
        </div>
        <div>
          <label htmlFor="pack_size" className="mb-1 block text-xs text-muted-foreground">
            Pack size
          </label>
          <input
            id="pack_size"
            name="pack_size"
            type="number"
            min={1}
            step={1}
            defaultValue={1}
            aria-invalid={Boolean(state.fieldErrors.pack_size)}
            className={`${FIELD_CLASS} font-mono`}
          />
          <FieldError message={state.fieldErrors.pack_size} />
        </div>
        <div className="flex items-end pb-2">
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input type="checkbox" name="is_preferred" className="size-4" />
            Preferred
          </label>
        </div>
      </div>

      <FormError message={state.formError} />

      <div className="mt-1">
        <SubmitButton />
      </div>
    </form>
  );
}
