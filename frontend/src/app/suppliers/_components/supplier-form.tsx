"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { FIELD_CLASS, FieldError, FormError } from "@/components/domain/form-field";
import { emptyFormState, type FormActionState } from "@/lib/api-error";
import type { components } from "@/lib/api/client";

type Supplier = components["schemas"]["SupplierRead"];

function SubmitButton({ label, pendingLabel }: { label: string; pendingLabel: string }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="flex h-control items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
    >
      {pending ? pendingLabel : label}
    </button>
  );
}

/**
 * Create or edit a supplier. One component for both, since the fields are
 * identical — only the action and the starting values differ.
 */
export function SupplierForm({
  action,
  supplier,
  submitLabel,
  submitPendingLabel,
}: {
  action: (state: FormActionState, formData: FormData) => Promise<FormActionState>;
  supplier?: Supplier;
  submitLabel: string;
  submitPendingLabel: string;
}) {
  const [state, formAction] = useActionState(action, emptyFormState);

  return (
    <form action={formAction} className="flex max-w-md flex-col gap-stack">
      <div>
        <label htmlFor="name" className="mb-1 block text-xs text-muted-foreground">
          Name
        </label>
        <input
          id="name"
          name="name"
          required
          defaultValue={supplier?.name}
          placeholder="e.g. Dairy Direct Ltd"
          aria-invalid={Boolean(state.fieldErrors.name)}
          className={FIELD_CLASS}
        />
        <FieldError message={state.fieldErrors.name} />
      </div>

      <div className="grid grid-cols-2 gap-stack">
        <div>
          <label
            htmlFor="contact_email"
            className="mb-1 block text-xs text-muted-foreground"
          >
            Contact email (optional)
          </label>
          <input
            id="contact_email"
            name="contact_email"
            type="email"
            defaultValue={supplier?.contact_email ?? undefined}
            aria-invalid={Boolean(state.fieldErrors.contact_email)}
            className={FIELD_CLASS}
          />
          <FieldError message={state.fieldErrors.contact_email} />
        </div>
        <div>
          <label
            htmlFor="contact_phone"
            className="mb-1 block text-xs text-muted-foreground"
          >
            Contact phone (optional)
          </label>
          <input
            id="contact_phone"
            name="contact_phone"
            defaultValue={supplier?.contact_phone ?? undefined}
            aria-invalid={Boolean(state.fieldErrors.contact_phone)}
            className={FIELD_CLASS}
          />
          <FieldError message={state.fieldErrors.contact_phone} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-stack">
        <div>
          <label
            htmlFor="lead_time_days"
            className="mb-1 block text-xs text-muted-foreground"
          >
            Lead time (days)
          </label>
          <input
            id="lead_time_days"
            name="lead_time_days"
            type="number"
            min={0}
            step={1}
            defaultValue={supplier?.lead_time_days ?? 0}
            aria-invalid={Boolean(state.fieldErrors.lead_time_days)}
            className={`${FIELD_CLASS} font-mono`}
          />
          <FieldError message={state.fieldErrors.lead_time_days} />
        </div>
        <div>
          <label
            htmlFor="minimum_order_value"
            className="mb-1 block text-xs text-muted-foreground"
          >
            Minimum order (Rs)
          </label>
          <input
            id="minimum_order_value"
            name="minimum_order_value"
            inputMode="decimal"
            defaultValue={supplier?.minimum_order_value ?? "0.00"}
            aria-invalid={Boolean(state.fieldErrors.minimum_order_value)}
            className={`${FIELD_CLASS} font-mono`}
          />
          <FieldError message={state.fieldErrors.minimum_order_value} />
        </div>
      </div>

      <FormError message={state.formError} />

      <div className="mt-1">
        <SubmitButton label={submitLabel} pendingLabel={submitPendingLabel} />
      </div>
    </form>
  );
}
