"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { deactivateSupplier } from "../actions";

/**
 * The one interactive control outside a `<form>` on this page. A small
 * client island rather than making the whole detail page client-rendered.
 */
export function DeactivateAction({ supplierId }: { supplierId: number }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        disabled={pending}
        onClick={() => {
          setError(null);
          startTransition(async () => {
            const result = await deactivateSupplier(supplierId);
            if (result) {
              setError(result.error);
            } else {
              router.refresh();
            }
          });
        }}
        className="flex h-control items-center rounded-(--radius) border border-border bg-card px-4 text-sm text-foreground disabled:opacity-50"
      >
        {pending ? "Deactivating…" : "Deactivate"}
      </button>
      {error && <span className="text-xs text-stock-out">{error}</span>}
    </div>
  );
}
