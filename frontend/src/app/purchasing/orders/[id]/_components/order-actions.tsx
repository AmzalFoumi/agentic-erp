"use client";

import { useState, useTransition } from "react";

import { cancelOrder, sendOrder } from "../actions";

/**
 * Send / Cancel, each disabled when the transition is illegal.
 *
 * Mirrors `LEGAL_TRANSITIONS` in `services/purchasing/orders.py` for the two
 * states this gate can reach: `draft` may send or cancel, `sent` may only
 * cancel. The server refuses an illegal transition regardless — a disabled
 * button here is the honest signal, not the enforcement.
 */
export function OrderActions({ orderId, status }: { orderId: number; status: string }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const canSend = status === "draft";
  const canCancel = status === "draft" || status === "sent";

  function run(action: () => Promise<{ error: string } | null>) {
    setError(null);
    startTransition(async () => {
      const result = await action();
      if (result) setError(result.error);
    });
  }

  if (!canSend && !canCancel) return null;

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex gap-2">
        {canSend && (
          <button
            type="button"
            disabled={pending}
            onClick={() => run(() => sendOrder(orderId))}
            className="flex h-control items-center rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {pending ? "Working…" : "Send"}
          </button>
        )}
        {canCancel && (
          <button
            type="button"
            disabled={pending}
            onClick={() => run(() => cancelOrder(orderId))}
            className="flex h-control items-center rounded-(--radius) border border-border bg-card px-4 text-sm text-foreground disabled:opacity-50"
          >
            {pending ? "Working…" : "Cancel"}
          </button>
        )}
      </div>
      {error && <span className="text-xs text-stock-out">{error}</span>}
    </div>
  );
}
