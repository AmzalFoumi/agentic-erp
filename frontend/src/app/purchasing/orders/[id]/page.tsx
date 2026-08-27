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
import { formatDate, formatDateTime } from "@/lib/format";

import { OrderActions } from "./_components/order-actions";

const HEAD = "h-auto px-cell-x py-cell-y";
const CELL = "px-cell-x py-0";

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  sent: "Sent",
  partially_received: "Partially received",
  received: "Received",
  cancelled: "Cancelled",
};

function BackToList() {
  return (
    <Link
      href="/purchasing/orders"
      className="mt-1 flex h-control items-center rounded-(--radius) border border-border bg-card px-4 text-sm text-foreground"
    >
      Back to orders
    </Link>
  );
}

export default async function PurchaseOrderDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: idParam } = await params;
  const id = Number(idParam);

  if (!Number.isInteger(id)) {
    return (
      <ApiErrorState
        title="Order not found"
        detail="That link doesn't point to a real purchase order."
        action={<BackToList />}
      />
    );
  }

  const { data: order, error } = await api.GET("/purchase-orders/{order_id}", {
    params: { path: { order_id: id } },
  });

  if (error) {
    return (
      <ApiErrorState
        title={error.error === "NotFoundError" ? "Order not found" : "Couldn't load order"}
        detail={error.detail}
        action={<BackToList />}
      />
    );
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-section flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold">Order #{order.id}</h1>
            <Badge variant="outline" className="border-transparent bg-secondary">
              {STATUS_LABELS[order.status] ?? order.status}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {order.expected_date
              ? `Expected ${formatDate(order.expected_date)}`
              : "Not yet placed — no expected date"}
          </p>
        </div>
        <OrderActions orderId={order.id} status={order.status} />
      </div>

      {order.notes && (
        <p className="mb-section rounded-(--radius) border border-border bg-card px-3 py-2 text-sm text-foreground">
          {order.notes}
        </p>
      )}

      <div className="mb-section table-scroll-fix overflow-y-auto rounded-(--radius) border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="bg-secondary">
              <TableHead className={HEAD}>Product</TableHead>
              <TableHead className={`${HEAD} text-right`}>Quantity</TableHead>
              <TableHead className={`${HEAD} text-right`}>Unit cost</TableHead>
              <TableHead className={`${HEAD} text-right`}>Line total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {order.lines.map((line) => (
              <TableRow key={line.id} className="h-row">
                <TableCell className={CELL}>
                  <Link
                    href={`/products/${line.product_id}`}
                    className="text-primary hover:underline"
                  >
                    Product #{line.product_id}
                  </Link>
                </TableCell>
                <TableCell data-numeric className={`${CELL} text-right font-mono`}>
                  {line.quantity_ordered}
                </TableCell>
                <TableCell className={`${CELL} text-right`}>
                  <MoneyDisplay value={line.unit_cost} />
                </TableCell>
                <TableCell className={`${CELL} text-right`}>
                  <MoneyDisplay value={line.line_total} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between rounded-(--radius) border border-border bg-card p-section text-sm">
        <span className="text-muted-foreground">
          Created {formatDateTime(order.created_at)} · {order.created_by ?? "system"}
        </span>
        <span className="font-semibold">
          Total <MoneyDisplay value={order.total_value} />
        </span>
      </div>
    </div>
  );
}
