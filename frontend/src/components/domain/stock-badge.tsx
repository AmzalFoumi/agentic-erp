import { Badge } from "@/components/ui/badge";

type StockStatusInput = {
  quantity_on_hand: number;
  needs_reorder: boolean;
};

/**
 * Three states, all read off the API — never recomputed. `stock-over` has
 * no field behind it yet (see DESIGN.md) so it is not a case here; adding
 * it later means adding a fourth branch, not inventing a threshold.
 */
function statusFor({ quantity_on_hand, needs_reorder }: StockStatusInput) {
  if (quantity_on_hand === 0) {
    return {
      label: "Out of stock",
      className: "bg-stock-out-surface text-stock-out",
    };
  }
  if (needs_reorder) {
    return {
      label: "Low stock",
      className: "bg-stock-low-surface text-stock-low",
    };
  }
  return {
    label: "In stock",
    className: "bg-stock-ok-surface text-stock-ok",
  };
}

export function StockBadge(props: StockStatusInput) {
  const status = statusFor(props);
  return (
    <Badge variant="outline" className={`border-transparent ${status.className}`}>
      {status.label}
    </Badge>
  );
}
