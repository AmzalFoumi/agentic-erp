"use client";

import { useState, useTransition } from "react";

import type { components } from "@/lib/api/client";

import { receiveOrder } from "../actions";

type PurchaseOrderLineRead = components["schemas"]["PurchaseOrderLineRead"];
type ReceiptLineCreate = components["schemas"]["ReceiptLineCreate"];

const FIELD_CLASS =
  "h-control w-full rounded-(--radius) border border-border bg-background px-2 text-sm font-mono";

type LineInput = {
  quantity_received: string;
  quantity_damaged: string;
  expiry_date: string;
  lot_code: string;
};

function emptyLineInput(quantityOrdered: number): LineInput {
  return {
    quantity_received: String(quantityOrdered),
    quantity_damaged: "0",
    expiry_date: "",
    lot_code: "",
  };
}

/**
 * Records what actually arrived for a `sent` order. Mirrors `OrderActions`'
 * useTransition pattern (gate 29) rather than the `useActionState`/FormData
 * pattern used elsewhere — the payload here is a structured array of lines,
 * not flat form fields.
 *
 * `expiry_date` has no default and is required on every line, per the
 * design's "no default" rule: an empty date must never silently submit.
 */
export function ReceiveForm({
  orderId,
  lines,
}: {
  orderId: number;
  lines: PurchaseOrderLineRead[];
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [inputs, setInputs] = useState<Record<number, LineInput>>(() =>
    Object.fromEntries(lines.map((line) => [line.id, emptyLineInput(line.quantity_ordered)])),
  );

  function updateLine(lineId: number, patch: Partial<LineInput>) {
    setInputs((prev) => ({ ...prev, [lineId]: { ...prev[lineId], ...patch } }));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const payload: ReceiptLineCreate[] = lines.map((line) => {
      const input = inputs[line.id];
      return {
        product_id: line.product_id,
        quantity_received: Number(input.quantity_received),
        quantity_damaged: Number(input.quantity_damaged),
        expiry_date: input.expiry_date,
        lot_code: input.lot_code,
      };
    });

    startTransition(async () => {
      const result = await receiveOrder(orderId, payload);
      if (result) setError(result.error);
    });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mb-section rounded-(--radius) border border-border bg-card p-section"
    >
      <h2 className="mb-stack text-sm font-semibold">Receive delivery</h2>
      <div className="flex flex-col gap-stack">
        {lines.map((line) => {
          const input = inputs[line.id];
          return (
            <div key={line.id} className="grid grid-cols-5 items-end gap-2">
              <div className="col-span-1 text-sm text-foreground">
                Product #{line.product_id}
                <div className="text-xs text-muted-foreground">
                  Ordered {line.quantity_ordered}
                </div>
              </div>
              <div>
                <label
                  htmlFor={`received-${line.id}`}
                  className="mb-1 block text-xs text-muted-foreground"
                >
                  Received
                </label>
                <input
                  id={`received-${line.id}`}
                  type="number"
                  min={0}
                  step={1}
                  required
                  value={input.quantity_received}
                  onChange={(e) => updateLine(line.id, { quantity_received: e.target.value })}
                  className={FIELD_CLASS}
                />
              </div>
              <div>
                <label
                  htmlFor={`damaged-${line.id}`}
                  className="mb-1 block text-xs text-muted-foreground"
                >
                  Damaged
                </label>
                <input
                  id={`damaged-${line.id}`}
                  type="number"
                  min={0}
                  step={1}
                  required
                  value={input.quantity_damaged}
                  onChange={(e) => updateLine(line.id, { quantity_damaged: e.target.value })}
                  className={FIELD_CLASS}
                />
              </div>
              <div>
                <label
                  htmlFor={`expiry-${line.id}`}
                  className="mb-1 block text-xs text-muted-foreground"
                >
                  Expiry date
                </label>
                <input
                  id={`expiry-${line.id}`}
                  type="date"
                  required
                  value={input.expiry_date}
                  onChange={(e) => updateLine(line.id, { expiry_date: e.target.value })}
                  className={FIELD_CLASS}
                />
              </div>
              <div>
                <label
                  htmlFor={`lot-${line.id}`}
                  className="mb-1 block text-xs text-muted-foreground"
                >
                  Lot code
                </label>
                <input
                  id={`lot-${line.id}`}
                  type="text"
                  required
                  value={input.lot_code}
                  onChange={(e) => updateLine(line.id, { lot_code: e.target.value })}
                  className={FIELD_CLASS}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-stack flex items-center gap-2">
        <button
          type="submit"
          disabled={pending}
          className="flex h-control items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {pending ? "Working…" : "Record receipt"}
        </button>
        {error && <span className="text-xs text-stock-out">{error}</span>}
      </div>
    </form>
  );
}
