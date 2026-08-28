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

import { setPreferred } from "../actions";

type SupplierProduct = components["schemas"]["SupplierProductRead"];
type Product = components["schemas"]["ProductRead"];

const HEAD = "h-auto px-cell-x py-cell-y";
const CELL = "px-cell-x py-0";

function PreferredCell({
  supplierId,
  link,
}: {
  supplierId: number;
  link: SupplierProduct;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="flex items-center gap-2">
      {link.is_preferred ? (
        <Badge variant="outline" className="border-transparent bg-stock-ok-surface text-stock-ok">
          Preferred
        </Badge>
      ) : (
        <button
          type="button"
          disabled={pending}
          onClick={() => {
            setError(null);
            startTransition(async () => {
              const result = await setPreferred(supplierId, link.id, true);
              if (result) setError(result.error);
            });
          }}
          className="h-control flex items-center rounded-(--radius) border border-border px-3 text-xs text-foreground disabled:opacity-50"
        >
          {pending ? "Working…" : "Make preferred"}
        </button>
      )}
      {error && <span className="text-xs text-stock-out">{error}</span>}
    </div>
  );
}

/**
 * This supplier's price list. `products` is the whole catalogue, passed
 * down from the server page rather than fetched again here, so a product's
 * SKU and name are readable next to its price without an extra round trip
 * per row.
 */
export function LinksTable({
  supplierId,
  links,
  products,
}: {
  supplierId: number;
  links: SupplierProduct[];
  products: Product[];
}) {
  const byId = new Map(products.map((product) => [product.id, product]));

  return (
    <div className="table-scroll-fix min-h-0 flex-1 overflow-y-auto rounded-(--radius) border border-border bg-card">
      <Table>
        <TableHeader className="sticky top-0 z-10">
          <TableRow className="bg-secondary">
            <TableHead className={HEAD}>Product</TableHead>
            <TableHead className={`${HEAD} text-right`}>Unit cost</TableHead>
            <TableHead className={`${HEAD} text-right`}>Pack size</TableHead>
            <TableHead className={HEAD}>Preference</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {links.map((link) => {
            const product = byId.get(link.product_id);
            return (
              <TableRow key={link.id} className="h-row">
                <TableCell className={CELL}>
                  {product ? (
                    <>
                      <span className="font-mono text-xs text-muted-foreground">
                        {product.sku}
                      </span>{" "}
                      {product.name}
                    </>
                  ) : (
                    // The product could have been referenced by an id that no
                    // longer resolves in this render's snapshot. Shown rather
                    // than hidden — a price list entry must not silently
                    // disappear.
                    <span className="text-muted-foreground">
                      Product #{link.product_id}
                    </span>
                  )}
                </TableCell>
                <TableCell className={`${CELL} text-right`}>
                  <MoneyDisplay value={link.unit_cost} />
                </TableCell>
                <TableCell data-numeric className={`${CELL} text-right font-mono`}>
                  {link.pack_size}
                </TableCell>
                <TableCell className={CELL}>
                  <PreferredCell supplierId={supplierId} link={link} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
