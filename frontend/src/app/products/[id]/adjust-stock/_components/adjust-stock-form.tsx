"use client";

import Link from "next/link";
import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import { FormError } from "@/components/domain/form-field";
import { emptyFormState } from "@/lib/api-error";

import { adjustStock } from "../actions";

function SubmitButton({ disabled }: { disabled: boolean }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending || disabled}
      className="flex h-control items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
    >
      {pending ? "Confirming…" : "Confirm adjustment"}
    </button>
  );
}

export function AdjustStockForm({
  id,
  currentQuantity,
}: {
  id: number;
  currentQuantity: number;
}) {
  const action = adjustStock.bind(null, id);
  const [state, formAction] = useActionState(action, emptyFormState);
  const [deltaInput, setDeltaInput] = useState("");

  const delta = deltaInput === "" ? 0 : Number(deltaInput);
  const hasInput = deltaInput !== "";
  const resulting = currentQuantity + delta;
  const isZero = hasInput && delta === 0;
  const isNegative = hasInput && resulting < 0;
  const rejected = isZero || isNegative;

  return (
    <form action={formAction} className="flex max-w-sm flex-col gap-stack">
      <div>
        <label htmlFor="delta" className="mb-1 block text-xs text-muted-foreground">
          Delta
        </label>
        <input
          id="delta"
          name="delta"
          type="number"
          step={1}
          value={deltaInput}
          onChange={(e) => setDeltaInput(e.target.value)}
          placeholder="e.g. 8 or -3"
          aria-invalid={rejected}
          className="h-control w-full rounded-(--radius) border border-input bg-card px-3 font-mono text-sm text-foreground aria-invalid:border-destructive"
        />
      </div>

      <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-center gap-2 rounded-(--radius) border border-border bg-card p-section text-center font-mono tabular-nums">
        <div>
          <div className="text-xl font-semibold">{currentQuantity}</div>
          <div className="text-xs font-sans text-muted-foreground">current</div>
        </div>
        <div className="text-muted-foreground">+</div>
        <div>
          <div className="text-xl font-semibold">
            {hasInput ? (delta > 0 ? `+${delta}` : delta) : "—"}
          </div>
          <div className="text-xs font-sans text-muted-foreground">delta</div>
        </div>
        <div className="text-muted-foreground">=</div>
        <div>
          <div
            className={`text-xl font-semibold ${rejected ? "text-destructive" : ""}`}
          >
            {hasInput ? resulting : currentQuantity}
          </div>
          <div className="text-xs font-sans text-muted-foreground">resulting</div>
        </div>
      </div>

      {isZero && (
        <div className="text-sm text-destructive">
          A delta of zero has no effect and is rejected.
        </div>
      )}
      {isNegative && (
        <div className="text-sm text-destructive">
          This would take stock below zero. Adjustment rejected.
        </div>
      )}

      <FormError message={state.formError} />

      <div className="mt-1 flex gap-2">
        <SubmitButton disabled={rejected} />
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
