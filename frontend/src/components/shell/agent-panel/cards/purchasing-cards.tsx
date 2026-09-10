"use client";

import Link from "next/link";

import type {
  DraftListOut,
  DraftOut,
  PurchaseOrderListOut,
  PurchaseOrderOut,
  ReorderBundleOut,
  ReorderLineOut,
  ReorderReportOut,
} from "@/lib/api/mcp-types";
import { ChatCard } from "./chat-card";
import { ChatCardTable, type ChatCardColumn } from "./chat-card-table";
import { FallbackCard } from "./fallback-card";
import { parseToolOutput } from "./parse-tool-output";
import { formatMoney } from "@/lib/format";

/* ---------- suggest_reorder_bundles ---------- */

function isReorderReportOut(v: unknown): v is ReorderReportOut {
  return (
    v != null &&
    typeof v === "object" &&
    Array.isArray((v as ReorderReportOut).bundles) &&
    Array.isArray((v as ReorderReportOut).unsourced) &&
    typeof (v as ReorderReportOut).total_value === "string"
  );
}

const BUNDLE_LINE_COLUMNS: ChatCardColumn<ReorderLineOut>[] = [
  { key: "name", header: "Product", cell: (l) => l.name },
  { key: "qty", header: "Order qty", numeric: true, cell: (l) => l.quantity },
  { key: "unit", header: "Unit cost", numeric: true, cell: (l) => formatMoney(l.unit_cost) },
  { key: "total", header: "Line total", numeric: true, cell: (l) => formatMoney(l.line_total) },
];

function BundleSection({ bundle }: { bundle: ReorderBundleOut }) {
  return (
    <div className="flex flex-col gap-1 rounded-(--radius) border border-border p-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-medium">{bundle.supplier_name}</span>
        <span className="text-xs text-muted-foreground tabular-nums">
          {formatMoney(bundle.bundle_value)}
          {bundle.below_minimum ? " · below minimum" : ""}
        </span>
      </div>
      <ChatCardTable
        columns={BUNDLE_LINE_COLUMNS}
        rows={bundle.lines}
        rowKey={(l) => String(l.product_id)}
        cap={20}
      />
    </div>
  );
}

export function ReorderBundlesCard({ output }: { output: unknown }) {
  const data = parseToolOutput(output);
  if (!isReorderReportOut(data)) return <FallbackCard output={output} />;

  return (
    <ChatCard title="Suggested reorder" headerRight={`${formatMoney(data.total_value)} total`}>
      {data.bundles.length === 0 ? (
        <p className="text-muted-foreground">Nothing needs reordering.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {data.bundles.map((b) => (
            <BundleSection key={b.supplier_id} bundle={b} />
          ))}
        </div>
      )}
      {data.unsourced.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {data.unsourced.length} item{data.unsourced.length === 1 ? "" : "s"} with no supplier:{" "}
          {data.unsourced.map((u) => u.name).join(", ")}
        </p>
      )}
      <Link href="/purchasing" className="self-start text-xs text-primary hover:underline">
        Open purchasing →
      </Link>
    </ChatCard>
  );
}

/* ---------- list_pending_drafts ---------- */

function isDraftListOut(v: unknown): v is DraftListOut {
  return (
    v != null &&
    typeof v === "object" &&
    Array.isArray((v as DraftListOut).drafts) &&
    (v as DraftListOut).drafts.every(
      (d) => d != null && typeof (d as DraftOut).draft_type === "string",
    )
  );
}

function draftSummary(draft: DraftOut): string {
  const payload = (draft.payload ?? {}) as Record<string, unknown>;
  const lines = Array.isArray(payload.lines) ? (payload.lines as unknown[]) : [];
  if (draft.draft_type === "SUPPLIER_REORDER") {
    const supplier = payload.supplier_id != null ? `supplier #${String(payload.supplier_id)}` : "a supplier";
    return `Reorder ${lines.length} item${lines.length === 1 ? "" : "s"} from ${supplier}`;
  }
  if (draft.draft_type === "BATCH_PRICE_MARKDOWN") {
    return `Mark down ${lines.length} lot${lines.length === 1 ? "" : "s"}`;
  }
  return draft.draft_type.replace(/_/g, " ").toLowerCase();
}

export function PendingDraftsCard({ output }: { output: unknown }) {
  const data = parseToolOutput(output);
  if (!isDraftListOut(data)) return <FallbackCard output={output} />;

  return (
    <ChatCard
      title="Pending approvals"
      headerRight={`${data.drafts.length} waiting`}
    >
      {data.drafts.length === 0 ? (
        <p className="text-muted-foreground">Nothing waiting for approval.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {data.drafts.map((d) => (
            <li
              key={d.id}
              className="flex flex-col gap-0.5 rounded-(--radius) border border-border p-2"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-medium">{draftSummary(d)}</span>
                <span className="text-xs text-muted-foreground">
                  {d.is_expired ? "expired" : d.status.toLowerCase()}
                </span>
              </div>
              {d.reasoning && (
                <span className="text-xs text-muted-foreground">{d.reasoning}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      <Link href="/approvals" className="self-start text-xs text-primary hover:underline">
        Open approvals →
      </Link>
    </ChatCard>
  );
}

/* ---------- create_action_draft / propose_* (single DraftOut) ---------- */

function isDraftOut(v: unknown): v is DraftOut {
  return (
    v != null &&
    typeof v === "object" &&
    typeof (v as DraftOut).draft_type === "string" &&
    typeof (v as DraftOut).status === "string" &&
    "payload" in (v as DraftOut)
  );
}

/**
 * The four draft-creating tools (create_action_draft, propose_spoilage_markdown,
 * propose_reorder_order, propose_delivery_receipt) run staging-only, so their
 * wire part has no approval object and would otherwise fall through to the
 * generic Result card. Show the same one-line summary PendingDraftsCard uses,
 * plus the money-at-stake line, and point at the approvals queue.
 */
export function DraftCard({ output }: { output: unknown }) {
  const d = parseToolOutput(output);
  if (!isDraftOut(d)) return <FallbackCard output={output} />;

  return (
    <ChatCard
      title="Draft proposed"
      headerRight={d.is_expired ? "expired" : d.status.toLowerCase()}
    >
      <div className="font-medium">{draftSummary(d)}</div>
      {d.reasoning && (
        <p className="text-xs text-muted-foreground">{d.reasoning}</p>
      )}
      {(d.cost_at_risk != null || d.projected_recovery != null) && (
        <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
          {d.cost_at_risk != null && <span>At risk: {formatMoney(d.cost_at_risk)}</span>}
          {d.projected_recovery != null && (
            <span>Recoverable: {formatMoney(d.projected_recovery)}</span>
          )}
        </div>
      )}
      <Link href="/approvals" className="self-start text-xs text-primary hover:underline">
        Review in approvals →
      </Link>
    </ChatCard>
  );
}

/* ---------- list_purchase_orders ---------- */

function isPurchaseOrderListOut(v: unknown): v is PurchaseOrderListOut {
  return (
    v != null &&
    typeof v === "object" &&
    Array.isArray((v as PurchaseOrderListOut).orders) &&
    typeof (v as PurchaseOrderListOut).total === "number"
  );
}

const PO_COLUMNS: ChatCardColumn<PurchaseOrderOut>[] = [
  { key: "id", header: "PO", cell: (o) => <span className="font-mono text-xs">#{o.id}</span> },
  { key: "supplier", header: "Supplier", numeric: true, cell: (o) => `#${o.supplier_id}` },
  { key: "status", header: "Status", cell: (o) => o.status.toLowerCase() },
  { key: "lines", header: "Lines", numeric: true, cell: (o) => o.lines.length },
  { key: "total", header: "Value", numeric: true, cell: (o) => formatMoney(o.total_value) },
];

export function PurchaseOrdersCard({ output }: { output: unknown }) {
  const data = parseToolOutput(output);
  if (!isPurchaseOrderListOut(data)) return <FallbackCard output={output} />;

  return (
    <ChatCard title="Purchase orders" headerRight={`${data.total} total`}>
      {data.orders.length === 0 ? (
        <p className="text-muted-foreground">No purchase orders.</p>
      ) : (
        <ChatCardTable
          columns={PO_COLUMNS}
          rows={data.orders}
          rowKey={(o) => String(o.id)}
          cap={5}
          overflow={{ href: "/purchasing/orders", label: () => `View all ${data.total} orders →` }}
        />
      )}
    </ChatCard>
  );
}
