"use client";

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { FieldError, FIELD_CLASS, FormError } from "@/components/domain/form-field";
import { emptyFormState } from "@/lib/api-error";

import { receiveLot } from "../actions";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="flex h-control items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
    >
      {pending ? "Adding…" : "Add lot"}
    </button>
  );
}

export function ReceiveLotForm({ id }: { id: number }) {
  const action = receiveLot.bind(null, id);
  const [state, formAction] = useActionState(action, emptyFormState);

  return (
    <form action={formAction} className="flex max-w-sm flex-col gap-stack">
      <div>
        <label htmlFor="lot_code" className="mb-1 block text-xs text-muted-foreground">
          Lot code
        </label>
        <input
          id="lot_code"
          name="lot_code"
          type="text"
          required
          maxLength={64}
          placeholder="e.g. M-2026-08-05"
          aria-invalid={Boolean(state.fieldErrors.lot_code)}
          className={`${FIELD_CLASS} font-mono`}
        />
        <FieldError message={state.fieldErrors.lot_code} />
      </div>

      <div>
        <label htmlFor="quantity" className="mb-1 block text-xs text-muted-foreground">
          Quantity
        </label>
        <input
          id="quantity"
          name="quantity"
          type="number"
          step={1}
          min={1}
          required
          placeholder="e.g. 30"
          aria-invalid={Boolean(state.fieldErrors.quantity)}
          className={`${FIELD_CLASS} font-mono`}
        />
        <FieldError message={state.fieldErrors.quantity} />
      </div>

      <div>
        <label htmlFor="expiry_date" className="mb-1 block text-xs text-muted-foreground">
          Expiry date <span className="text-muted-foreground">(optional)</span>
        </label>
        <input
          id="expiry_date"
          name="expiry_date"
          type="date"
          aria-invalid={Boolean(state.fieldErrors.expiry_date)}
          className={FIELD_CLASS}
        />
        <FieldError message={state.fieldErrors.expiry_date} />
        <p className="mt-1 text-xs text-muted-foreground">
          Leave blank if unknown. Stock with no expiry is sold last and never
          marked down.
        </p>
      </div>

      <div>
        <label htmlFor="cost_price" className="mb-1 block text-xs text-muted-foreground">
          Unit cost <span className="text-muted-foreground">(optional)</span>
        </label>
        <input
          id="cost_price"
          name="cost_price"
          type="number"
          step="0.01"
          min="0"
          placeholder="uses the product's cost price"
          aria-invalid={Boolean(state.fieldErrors.cost_price)}
          className={`${FIELD_CLASS} font-mono`}
        />
        <FieldError message={state.fieldErrors.cost_price} />
        <p className="mt-1 text-xs text-muted-foreground">
          What one unit cost on this delivery. Frozen on the lot once set.
        </p>
      </div>

      <FormError message={state.formError} />

      <div className="mt-1 flex gap-2">
        <SubmitButton />
        <Link
          href={`/products/${id}`}
          className="flex h-control items-center rounded-(--radius) border border-border bg-card px-4 text-sm text-foreground"
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}
