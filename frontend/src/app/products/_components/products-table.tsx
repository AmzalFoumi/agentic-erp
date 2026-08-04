import { MoneyDisplay } from "@/components/domain/money-display";
import { StockBadge } from "@/components/domain/stock-badge";
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

type Product = components["schemas"]["ProductRead"];

// shadcn's TableHead/TableCell defaults hardcode p-2 / h-10. DESIGN.md's
// density rule is "no component hardcodes padding, gap, or row height," so
// every cell overrides those with the token classes instead.
const HEAD = "h-auto px-cell-x py-cell-y";
const CELL = "px-cell-x py-0";

export function ProductsTable({ products }: { products: Product[] }) {
  return (
    <div className="rounded-(--radius) border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow className="bg-secondary">
            <TableHead className={HEAD}>SKU</TableHead>
            <TableHead className={HEAD}>Name</TableHead>
            <TableHead className={HEAD}>Category</TableHead>
            <TableHead className={`${HEAD} text-right`}>Cost</TableHead>
            <TableHead className={`${HEAD} text-right`}>Sell</TableHead>
            <TableHead className={`${HEAD} text-right`}>Stock</TableHead>
            <TableHead className={HEAD}>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {products.map((product) => (
            <ClickableRow key={product.id} href={`/products/${product.id}`}>
              <TableCell className={`${CELL} font-mono text-sm`}>
                {product.sku}
              </TableCell>
              <TableCell className={CELL}>{product.name}</TableCell>
              <TableCell className={`${CELL} text-muted-foreground`}>
                {product.category ?? "—"}
              </TableCell>
              <TableCell className={`${CELL} text-right`}>
                <MoneyDisplay value={product.cost_price} />
              </TableCell>
              <TableCell className={`${CELL} text-right`}>
                <MoneyDisplay value={product.sell_price} />
              </TableCell>
              <TableCell data-numeric className={`${CELL} text-right font-mono`}>
                {product.quantity_on_hand}
              </TableCell>
              <TableCell className={CELL}>
                <StockBadge
                  quantity_on_hand={product.quantity_on_hand}
                  needs_reorder={product.needs_reorder}
                />
              </TableCell>
            </ClickableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
