"use client";

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { FIELD_CLASS, FieldError, FormError } from "@/components/domain/form-field";
import { emptyFormState } from "@/lib/api-error";
import type { components } from "@/lib/api/client";

import { updateProduct } from "../actions";

type Product = components["schemas"]["ProductRead"];

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="flex h-control items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
    >
      {pending ? "Saving…" : "Save changes"}
    </button>
  );
}

export function EditProductForm({ product }: { product: Product }) {
  const action = updateProduct.bind(null, product.id);
  const [state, formAction] = useActionState(action, emptyFormState);

  return (
    <form action={formAction} className="flex max-w-md flex-col gap-stack">
      <div>
        <div className="mb-1 text-xs text-muted-foreground">SKU</div>
        {/* Read-only text, not a disabled input — a disabled input implies
            it could be enabled. sku is not updatable via PATCH. */}
        <div className="py-2 font-mono text-sm">{product.sku}</div>
      </div>

      <div>
        <label htmlFor="name" className="mb-1 block text-xs text-muted-foreground">
          Name
        </label>
        <input
          id="name"
          name="name"
          required
          defaultValue={product.name}
          aria-invalid={Boolean(state.fieldErrors.name)}
          className={FIELD_CLASS}
        />
        <FieldError message={state.fieldErrors.name} />
      </div>

      <div>
        <label htmlFor="category" className="mb-1 block text-xs text-muted-foreground">
          Category
        </label>
        <input
          id="category"
          name="category"
          defaultValue={product.category ?? ""}
          aria-invalid={Boolean(state.fieldErrors.category)}
          className={FIELD_CLASS}
        />
        <FieldError message={state.fieldErrors.category} />
      </div>

      <div>
        <label htmlFor="unit" className="mb-1 block text-xs text-muted-foreground">
          Unit
        </label>
        <input
          id="unit"
          name="unit"
          defaultValue={product.unit}
          aria-invalid={Boolean(state.fieldErrors.unit)}
          className={FIELD_CLASS}
        />
        <FieldError message={state.fieldErrors.unit} />
      </div>

      <div className="grid grid-cols-2 gap-stack">
        <div>
          <label htmlFor="cost_price" className="mb-1 block text-xs text-muted-foreground">
            Cost price (Rs)
          </label>
          <input
            id="cost_price"
            name="cost_price"
            inputMode="decimal"
            defaultValue={product.cost_price}
            aria-invalid={Boolean(state.fieldErrors.cost_price)}
            className={`${FIELD_CLASS} font-mono`}
          />
          <FieldError message={state.fieldErrors.cost_price} />
        </div>
        <div>
          <label htmlFor="sell_price" className="mb-1 block text-xs text-muted-foreground">
            Sell price (Rs)
          </label>
          <input
            id="sell_price"
            name="sell_price"
            inputMode="decimal"
            defaultValue={product.sell_price}
            aria-invalid={Boolean(state.fieldErrors.sell_price)}
            className={`${FIELD_CLASS} font-mono`}
          />
          <FieldError message={state.fieldErrors.sell_price} />
        </div>
      </div>

      <div>
        <label htmlFor="reorder_level" className="mb-1 block text-xs text-muted-foreground">
          Reorder level
        </label>
        <input
          id="reorder_level"
          name="reorder_level"
          type="number"
          min={0}
          step={1}
          defaultValue={product.reorder_level}
          aria-invalid={Boolean(state.fieldErrors.reorder_level)}
          className={`${FIELD_CLASS} font-mono w-1/2`}
        />
        <FieldError message={state.fieldErrors.reorder_level} />
      </div>

      <FormError message={state.formError} />

      <div className="mt-1 flex gap-2">
        <SubmitButton />
        <Link
          href={`/products/${product.id}`}
          className="flex h-control items-center rounded-(--radius) border border-border bg-card px-4 text-sm text-foreground"
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}
