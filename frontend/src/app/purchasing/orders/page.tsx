import Link from "next/link";

import { ApiErrorState } from "@/components/domain/api-error-state";
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
import { api } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

const HEAD = "h-auto px-cell-x py-cell-y";
const CELL = "px-cell-x py-0";

const STATUSES = ["draft", "sent", "partially_received", "received", "cancelled"] as const;

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  sent: "Sent",
  partially_received: "Partially received",
  received: "Received",
  cancelled: "Cancelled",
};

/**
 * Every purchase order, newest first, with a status filter.
 *
 * A Server Component reading the filter from the URL's own query string —
 * the same shape as /products' search box — so a filtered view is a
 * shareable, bookmarkable link rather than client-only state.
 */
export default async function PurchaseOrdersPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;

  const { data, error } = await api.GET("/purchase-orders", {
    params: { query: { status: status || undefined, limit: 100, offset: 0 } },
  });

  if (error) {
    return <ApiErrorState title="Couldn't load purchase orders" detail={error.detail} />;
  }

  const { items, total } = data;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-section flex shrink-0 items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Purchase orders</h1>
          <p className="text-sm text-muted-foreground">{total} order(s)</p>
        </div>
        <div className="flex gap-2">
          <Link
            href="/purchasing/orders"
            className={`h-control flex items-center rounded-(--radius) border px-3 text-xs ${
              !status ? "border-primary bg-secondary" : "border-border text-muted-foreground"
            }`}
          >
            All
          </Link>
          {STATUSES.map((value) => (
            <Link
              key={value}
              href={`/purchasing/orders?status=${value}`}
              className={`h-control flex items-center rounded-(--radius) border px-3 text-xs ${
                status === value
                  ? "border-primary bg-secondary"
                  : "border-border text-muted-foreground"
              }`}
            >
              {STATUS_LABELS[value]}
            </Link>
          ))}
        </div>
      </div>

      {items.length === 0 ? (
        <div className="rounded-(--radius) border border-dashed border-border p-16 text-center">
          <div className="text-sm font-semibold">No orders</div>
          <div className="mt-1 text-sm text-muted-foreground">
            {status
              ? `Nothing is ${STATUS_LABELS[status]?.toLowerCase() ?? status}.`
              : "Propose a bundle from Purchasing and approve it to raise one."}
          </div>
        </div>
      ) : (
        <div className="table-scroll-fix min-h-0 flex-1 overflow-y-auto rounded-(--radius) border border-border bg-card">
          <Table>
            <TableHeader className="sticky top-0 z-10">
              <TableRow className="bg-secondary">
                <TableHead className={HEAD}>Order</TableHead>
                <TableHead className={HEAD}>Status</TableHead>
                <TableHead className={HEAD}>Expected</TableHead>
                <TableHead className={`${HEAD} text-right`}>Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((order) => (
                <TableRow key={order.id} className="h-row">
                  <TableCell className={CELL}>
                    <Link
                      href={`/purchasing/orders/${order.id}`}
                      className="text-primary hover:underline"
                    >
                      #{order.id}
                    </Link>
                  </TableCell>
                  <TableCell className={CELL}>
                    <Badge variant="outline" className="border-transparent bg-secondary">
                      {STATUS_LABELS[order.status] ?? order.status}
                    </Badge>
                  </TableCell>
                  <TableCell className={`${CELL} text-muted-foreground`}>
                    {order.expected_date ? formatDate(order.expected_date) : "—"}
                  </TableCell>
                  <TableCell className={`${CELL} text-right`}>
                    <MoneyDisplay value={order.total_value} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
