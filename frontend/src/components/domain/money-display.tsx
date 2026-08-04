import { formatMoney } from "@/lib/format";

/**
 * Right-aligned, tabular, formatted from the wire string — never a bare
 * number. See frontend/DESIGN.md's Money section.
 */
export function MoneyDisplay({ value }: { value: string }) {
  return (
    <span data-numeric className="font-mono tabular-nums">
      {formatMoney(value)}
    </span>
  );
}
