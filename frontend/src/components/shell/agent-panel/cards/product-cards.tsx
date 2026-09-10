"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import type { ProductListOut, ProductOut } from "@/lib/api/mcp-types";
import { ChatCard } from "./chat-card";
import { ChatCardTable, type ChatCardColumn } from "./chat-card-table";
import { FallbackCard } from "./fallback-card";
import { parseToolOutput } from "./parse-tool-output";
import { formatMoney } from "@/lib/format";
import { StockBadge } from "@/components/domain/stock-badge";

function isProductOut(v: unknown): v is ProductOut {
  return (
    v != null &&
    typeof v === "object" &&
    typeof (v as ProductOut).sku === "string" &&
    typeof (v as ProductOut).name === "string" &&
    typeof (v as ProductOut).sell_price === "string" &&
    typeof (v as ProductOut).quantity_on_hand === "number"
  );
}

function isProductListOut(v: unknown): v is ProductListOut {
  return (
    v != null &&
    typeof v === "object" &&
    Array.isArray((v as ProductListOut).products) &&
    typeof (v as ProductListOut).total === "number" &&
    (v as ProductListOut).products.every(isProductOut)
  );
}

const PRODUCT_COLUMNS: ChatCardColumn<ProductOut>[] = [
  { key: "sku", header: "SKU", cell: (p) => <span className="font-mono text-xs">{p.sku}</span> },
  { key: "name", header: "Name", cell: (p) => p.name },
  { key: "qty", header: "On hand", numeric: true, cell: (p) => p.quantity_on_hand },
  {
    key: "status",
    header: "Status",
    cell: (p) => (
      <StockBadge quantity_on_hand={p.quantity_on_hand} needs_reorder={p.needs_reorder} />
    ),
  },
  { key: "price", header: "Sell price", numeric: true, cell: (p) => formatMoney(p.sell_price) },
];

export function ProductListCard({ output }: { output: unknown }) {
  const data = parseToolOutput(output);
  if (!isProductListOut(data)) return <FallbackCard output={output} />;

  return (
    <ChatCard title="Products" headerRight={`${data.total} total`}>
      <ChatCardTable
        columns={PRODUCT_COLUMNS}
        rows={data.products}
        rowKey={(p) => p.sku}
        cap={5}
        overflow={{
          href: "/products",
          label: () => `View all ${data.total} in Products →`,
        }}
      />
    </ChatCard>
  );
}

export function ProductCard({ output }: { output: unknown }) {
  const p = parseToolOutput(output);
  if (!isProductOut(p)) return <FallbackCard output={output} />;

  const rows: [string, ReactNode][] = [
    // eslint-disable-next-line react/jsx-key
    ["SKU", <span className="font-mono text-xs">{p.sku}</span>],
    ["Category", p.category ?? "—"],
    // eslint-disable-next-line react/jsx-key
    ["On hand", <span className="tabular-nums">{p.quantity_on_hand}</span>],
    // eslint-disable-next-line react/jsx-key
    ["Reorder level", <span className="tabular-nums">{p.reorder_level}</span>],
    // eslint-disable-next-line react/jsx-key
    ["Cost price", <span className="tabular-nums">{formatMoney(p.cost_price)}</span>],
    // eslint-disable-next-line react/jsx-key
    ["Sell price", <span className="tabular-nums">{formatMoney(p.sell_price)}</span>],
  ];

  return (
    <ChatCard
      title={p.name}
      headerRight={
        <StockBadge quantity_on_hand={p.quantity_on_hand} needs_reorder={p.needs_reorder} />
      }
    >
      <dl className="grid grid-cols-2 gap-x-2 gap-y-1" data-numeric>
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <Link
        href={`/products/${p.id}`}
        className="self-start text-xs text-primary hover:underline"
      >
        Open in Products →
      </Link>
    </ChatCard>
  );
}
