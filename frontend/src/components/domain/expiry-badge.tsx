import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/format";

type ExpiryInput = {
  /** The lot's expiry date as the wire string "YYYY-MM-DD", or null when unknown. */
  expiryDate: string | null;
  /** Whether the lot is expired — read off the API, never recomputed here. */
  isExpired: boolean;
};

/**
 * One lot's expiry, as a coloured pill.
 *
 * The "expired or not" decision is the server's (`LotRead.is_expired`), not
 * this component's. Comparing `expiry_date` to `new Date()` here would use the
 * viewer's clock and their timezone, and a carton that goes off tomorrow could
 * then read as "expired" for someone a few hours behind. So we only render
 * what the API already decided, and the date itself is split, never parsed —
 * see `formatDate`.
 */
function toneFor({ expiryDate, isExpired }: ExpiryInput) {
  if (isExpired) {
    return { label: "Expired", className: "bg-stock-out-surface text-stock-out" };
  }
  if (expiryDate === null) {
    return { label: "No expiry", className: "bg-muted text-muted-foreground" };
  }
  return {
    label: `Expires ${formatDate(expiryDate)}`,
    className: "bg-stock-ok-surface text-stock-ok",
  };
}

export function ExpiryBadge(props: ExpiryInput) {
  const tone = toneFor(props);
  return (
    <Badge variant="outline" className={`border-transparent ${tone.className}`}>
      {tone.label}
    </Badge>
  );
}
