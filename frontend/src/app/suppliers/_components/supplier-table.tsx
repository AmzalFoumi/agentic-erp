"use client";

import { useState, useTransition } from "react";

import { MoneyDisplay } from "@/components/domain/money-display";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { components } from "@/lib/api/client";

import { ClickableRow } from "./clickable-row";
import { deactivateSupplier } from "../actions";

type Supplier = components["schemas"]["SupplierRead"];

const HEAD = "h-auto px-cell-x py-cell-y";
const CELL = "px-cell-x py-0";

function DeactivateButton({ supplier }: { supplier: Supplier }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  if (!supplier.is_active) {
    return (
      <Badge variant="outline" className="border-transparent bg-muted text-muted-foreground">
        Inactive
      </Badge>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        disabled={pending}
        onClick={(event) => {
          // A row click navigates to the detail page; this button must not
          // also trigger that.
          event.stopPropagation();
          setError(null);
          startTransition(async () => {
            const result = await deactivateSupplier(supplier.id);
            if (result) setError(result.error);
          });
        }}
        className="h-control flex items-center rounded-(--radius) border border-border px-3 text-xs text-foreground disabled:opacity-50"
      >
        {pending ? "Deactivating…" : "Deactivate"}
      </button>
      {error && <span className="text-xs text-stock-out">{error}</span>}
    </div>
  );
}

export function SupplierTable({ suppliers }: { suppliers: Supplier[] }) {
  return (
    <div className="table-scroll-fix min-h-0 flex-1 overflow-y-auto rounded-(--radius) border border-border bg-card">
      <Table>
        <TableHeader className="sticky top-0 z-10">
          <TableRow className="bg-secondary">
            <TableHead className={HEAD}>Name</TableHead>
            <TableHead className={HEAD}>Contact</TableHead>
            <TableHead className={`${HEAD} text-right`}>Lead time</TableHead>
            <TableHead className={`${HEAD} text-right`}>Minimum order</TableHead>
            <TableHead className={HEAD}>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {suppliers.map((supplier) => (
            <ClickableRow key={supplier.id} href={`/suppliers/${supplier.id}`}>
              <TableCell className={CELL}>{supplier.name}</TableCell>
              <TableCell className={`${CELL} text-muted-foreground`}>
                {supplier.contact_email ?? supplier.contact_phone ?? "—"}
              </TableCell>
              <TableCell data-numeric className={`${CELL} text-right font-mono`}>
                {supplier.lead_time_days} day{supplier.lead_time_days === 1 ? "" : "s"}
              </TableCell>
              <TableCell className={`${CELL} text-right`}>
                <MoneyDisplay value={supplier.minimum_order_value} />
              </TableCell>
              <TableCell className={CELL}>
                <DeactivateButton supplier={supplier} />
              </TableCell>
            </ClickableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
