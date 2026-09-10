"use client";

import type {
  LotListOut,
  LotOut,
  SpoilageItemOut,
  SpoilageReportOut,
} from "@/lib/api/mcp-types";
import { ChatCard } from "./chat-card";
import { ChatCardTable, type ChatCardColumn } from "./chat-card-table";
import { FallbackCard } from "./fallback-card";
import { parseToolOutput } from "./parse-tool-output";
import { formatDate, formatDaysRemaining, formatMoney } from "@/lib/format";

function isSpoilageReportOut(v: unknown): v is SpoilageReportOut {
  return (
    v != null &&
    typeof v === "object" &&
    Array.isArray((v as SpoilageReportOut).items) &&
    typeof (v as SpoilageReportOut).total_cost_at_risk === "string" &&
    typeof (v as SpoilageReportOut).scanned_on === "string"
  );
}

function isLotListOut(v: unknown): v is LotListOut {
  return (
    v != null &&
    typeof v === "object" &&
    Array.isArray((v as LotListOut).lots) &&
    (v as LotListOut).lots.every(
      (l) => l != null && typeof (l as LotOut).lot_code === "string",
    )
  );
}

const SPOILAGE_COLUMNS: ChatCardColumn<SpoilageItemOut>[] = [
  { key: "product", header: "Product", cell: (i) => i.product_name },
  { key: "lot", header: "Lot", cell: (i) => <span className="font-mono text-xs">{i.lot_code}</span> },
  { key: "expiry", header: "Expires", cell: (i) => formatDaysRemaining(i.days_remaining) },
  { key: "qty", header: "Qty", numeric: true, cell: (i) => i.quantity },
  {
    key: "price",
    header: "Now → markdown",
    numeric: true,
    cell: (i) =>
      i.discount_percent >= 100
        ? `${formatMoney(i.current_price)} → write off`
        : `${formatMoney(i.current_price)} → ${formatMoney(i.proposed_price)}`,
  },
  {
    key: "risk",
    header: "At risk",
    numeric: true,
    cell: (i) => formatMoney(i.cost_at_risk),
  },
];

export function SpoilageCard({ output }: { output: unknown }) {
  const data = parseToolOutput(output);
  if (!isSpoilageReportOut(data)) return <FallbackCard output={output} />;

  return (
    <ChatCard
      title="Spoilage risk"
      headerRight={`scanned ${formatDate(data.scanned_on)} · ${data.within_days}d window`}
    >
      {data.items.length === 0 ? (
        <p className="text-muted-foreground">Nothing at risk in the next {data.within_days} days.</p>
      ) : (
        <>
          <ChatCardTable
            columns={SPOILAGE_COLUMNS}
            rows={data.items}
            rowKey={(i) => String(i.lot_id)}
            cap={6}
            overflow={{
              href: "/inventory/spoilage",
              label: () => "Open spoilage review →",
            }}
          />
          <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
            <span>Total at risk: {formatMoney(data.total_cost_at_risk)}</span>
            <span>Recoverable: {formatMoney(data.total_projected_recovery)}</span>
          </div>
        </>
      )}
    </ChatCard>
  );
}

const LOT_COLUMNS: ChatCardColumn<LotOut>[] = [
  { key: "code", header: "Lot", cell: (l) => <span className="font-mono text-xs">{l.lot_code}</span> },
  {
    key: "expiry",
    header: "Expiry",
    cell: (l) =>
      l.expiry_date ? formatDate(l.expiry_date) : <span className="text-muted-foreground">—</span>,
  },
  { key: "qty", header: "Qty", numeric: true, cell: (l) => l.quantity },
  { key: "cost", header: "Cost", numeric: true, cell: (l) => formatMoney(l.cost_price) },
];

export function LotsCard({ output }: { output: unknown }) {
  const data = parseToolOutput(output);
  if (!isLotListOut(data)) return <FallbackCard output={output} />;

  // Soonest expiry first; nulls (no expiry) last.
  const lots = [...data.lots].sort((a, b) => {
    if (!a.expiry_date) return 1;
    if (!b.expiry_date) return -1;
    return a.expiry_date.localeCompare(b.expiry_date);
  });

  return (
    <ChatCard title="Stock lots" headerRight={`${data.lots.length} ${data.lots.length === 1 ? "lot" : "lots"}`}>
      {lots.length === 0 ? (
        <p className="text-muted-foreground">No lots on record.</p>
      ) : (
        <ChatCardTable
          columns={LOT_COLUMNS}
          rows={lots}
          rowKey={(l) => String(l.lot_id)}
          cap={6}
          overflow={
            lots[0]
              ? { href: `/products/${lots[0].product_id}`, label: () => "Open product →" }
              : undefined
          }
        />
      )}
    </ChatCard>
  );
}
