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
