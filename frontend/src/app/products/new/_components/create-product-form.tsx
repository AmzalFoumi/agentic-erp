"use client";

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { FIELD_CLASS, FieldError, FormError } from "@/components/domain/form-field";
import { emptyFormState } from "@/lib/api-error";

import { createProduct } from "../actions";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="flex h-control items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
    >
      {pending ? "Creating…" : "Create product"}
    </button>
  );
}

export function CreateProductForm() {
  const [state, formAction] = useActionState(createProduct, emptyFormState);

  return (
    <form action={formAction} className="flex max-w-md flex-col gap-stack">
      <div>
        <label htmlFor="sku" className="mb-1 block text-xs text-muted-foreground">
          SKU
        </label>
        <input
          id="sku"
          name="sku"
          required
          aria-invalid={Boolean(state.fieldErrors.sku)}
          className={FIELD_CLASS}
        />
        <FieldError message={state.fieldErrors.sku} />
      </div>

      <div>
        <label htmlFor="name" className="mb-1 block text-xs text-muted-foreground">
          Name
        </label>
        <input
          id="name"
          name="name"
          required
          placeholder="e.g. Sourdough loaf 800g"
          aria-invalid={Boolean(state.fieldErrors.name)}
          className={FIELD_CLASS}
        />
        <FieldError message={state.fieldErrors.name} />
      </div>

      <div>
        <label htmlFor="category" className="mb-1 block text-xs text-muted-foreground">
          Category (optional)
        </label>
        <input
          id="category"
          name="category"
          placeholder="e.g. Bakery"
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
          defaultValue="piece"
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
            defaultValue="0.00"
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
            defaultValue="0.00"
            aria-invalid={Boolean(state.fieldErrors.sell_price)}
            className={`${FIELD_CLASS} font-mono`}
          />
          <FieldError message={state.fieldErrors.sell_price} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-stack">
        <div>
          <label
            htmlFor="quantity_on_hand"
            className="mb-1 block text-xs text-muted-foreground"
          >
            Opening stock
          </label>
          <input
            id="quantity_on_hand"
            name="quantity_on_hand"
            type="number"
            min={0}
            step={1}
            defaultValue={0}
            aria-invalid={Boolean(state.fieldErrors.quantity_on_hand)}
            className={`${FIELD_CLASS} font-mono`}
          />
          <FieldError message={state.fieldErrors.quantity_on_hand} />
        </div>
        <div>
          <label
            htmlFor="reorder_level"
            className="mb-1 block text-xs text-muted-foreground"
          >
            Reorder level
          </label>
          <input
            id="reorder_level"
            name="reorder_level"
            type="number"
            min={0}
            step={1}
            defaultValue={0}
            aria-invalid={Boolean(state.fieldErrors.reorder_level)}
            className={`${FIELD_CLASS} font-mono`}
          />
          <FieldError message={state.fieldErrors.reorder_level} />
        </div>
      </div>

      <FormError message={state.formError} />

      <div className="mt-1 flex gap-2">
        <SubmitButton />
        <Link
          href="/products"
          className="flex h-control items-center rounded-(--radius) border border-border bg-card px-4 text-sm text-foreground"
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}
