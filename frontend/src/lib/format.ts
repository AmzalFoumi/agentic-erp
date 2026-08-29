/**
 * Money and timestamp formatting, decided once — see frontend/DESIGN.md.
 * Every screen imports from here rather than reinventing it.
 */

/**
 * "420.50" -> "Rs 420.50", "4588.00" -> "Rs 4,588.00".
 *
 * Deliberately no `Number()`/`parseFloat` anywhere in this function. The
 * wire value is already the exact string to show; grouping the integer part
 * is a regex over digits, not arithmetic, so there is nothing here that can
 * reintroduce the float64 precision loss the string encoding exists to
 * prevent. See the hard rule in DESIGN.md.
 */
export function formatMoney(value: string): string {
  const negative = value.startsWith("-");
  const unsigned = negative ? value.slice(1) : value;
  const [whole, fraction = ""] = unsigned.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const cents = fraction.padEnd(2, "0").slice(0, 2);
  return `Rs ${negative ? "-" : ""}${grouped}.${cents}`;
}

/**
 * A price that can vary by lot, shown as one figure or a range.
 *
 * The price a customer pays now lives on the lot, so a product has a spread
 * rather than a single number: `min` and `max` are the server-computed
 * roll-ups over the lots that still have stock. When they are null (the
 * product has no such lots) we fall back to `fallback`, the catalogue price.
 *
 * All string comparison and `formatMoney` — no `Number()` on money, per the
 * DESIGN.md rule. `min === max` is a safe string compare because both come
 * from the same `Numeric(10,2)` column, so "4.00" is never "4" here.
 */
export function priceRange(
  min: string | null,
  max: string | null,
  fallback: string,
): string {
  if (min === null || max === null) return formatMoney(fallback);
  if (min === max) return formatMoney(min);
  return `${formatMoney(min)} – ${formatMoney(max)}`;
}

/**
 * Absolute, Asia/Colombo, to the minute — never relative, never the
 * browser's zone. See DESIGN.md's Timestamps section for why.
 */
export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat("en-LK", {
    timeZone: "Asia/Colombo",
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

/**
 * "2026-08-29" -> "29 Aug 2026". A calendar day, with no time and no zone
 * conversion.
 *
 * Deliberately NOT `formatDateTime`, and deliberately not `new Date(iso)`
 * either. An expiry date is a calendar day, not an instant: `new Date(
 * "2026-08-29")` is parsed as midnight **UTC**, which in Asia/Colombo is
 * 05:30 on the 29th — but in any zone behind UTC it renders as the 28th. A
 * carton that expires tomorrow showing as expiring today is the kind of bug
 * that only appears for some users, in some timezones, some of the time.
 *
 * So the string is split, never parsed.
 */
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  const name = MONTHS[Number(month) - 1] ?? month;
  return `${Number(day)} ${name} ${year}`;
}

/**
 * "in 2 days", "tomorrow", "today", "3 days ago".
 *
 * Takes the day count the *server* calculated rather than working it out from
 * the browser's clock. Two clients in two timezones must not disagree about
 * whether stock expires today, and the server is the only one that can settle
 * that.
 */
export function formatDaysRemaining(days: number): string {
  if (days < 0) return `${Math.abs(days)} day${days === -1 ? "" : "s"} ago`;
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  return `in ${days} days`;
}
