"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { useChatMode } from "../chat-mode-context";
import { cn } from "@/lib/utils";

export type ChatCardColumn<Row> = {
  key: string;
  header: string;
  cell: (row: Row) => ReactNode;
  numeric?: boolean;
};

/**
 * A dense read-only table for a response card. Expanded panel: a real table
 * with a header row. Docked panel (256px rail): each row becomes a stacked
 * label/value block, because a five-column table does not fit 256px. One
 * component, both layouts — cards never think about panel width.
 *
 * `cap` caps the visible rows; `overflow` renders a "view all" link when rows
 * were hidden. tabular-nums comes from the `data-numeric` attribute (see
 * globals.css) plus per-column `numeric`.
 */
export function ChatCardTable<Row>({
  columns,
  rows,
  rowKey,
  cap = 5,
  overflow,
}: {
  columns: ChatCardColumn<Row>[];
  rows: Row[];
  rowKey: (row: Row, index: number) => string;
  cap?: number;
  overflow?: { href: string; label: (hiddenCount: number) => string };
}) {
  const mode = useChatMode();
  const shown = rows.slice(0, cap);
  const hidden = rows.length - shown.length;

  const overflowLink =
    overflow && hidden > 0 ? (
      <Link href={overflow.href} className="text-xs text-primary hover:underline">
        {overflow.label(hidden)}
      </Link>
    ) : null;

  if (mode === "docked") {
    return (
      <div className="flex flex-col gap-2">
        {shown.map((row, i) => (
          <div
            key={rowKey(row, i)}
            className="flex flex-col gap-0.5 rounded-(--radius) border border-border p-2"
            data-numeric
          >
            {columns.map((col) => (
              <div key={col.key} className="flex justify-between gap-2">
                <span className="text-muted-foreground">{col.header}</span>
                <span className={cn(col.numeric && "tabular-nums")}>{col.cell(row)}</span>
              </div>
            ))}
          </div>
        ))}
        {overflowLink}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-numeric>
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cn("py-1 pr-3 font-medium", col.numeric && "text-right")}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, i) => (
              <tr key={rowKey(row, i)} className="border-b border-border last:border-0">
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={cn(
                      "py-1 pr-3 align-top",
                      col.numeric && "text-right tabular-nums",
                    )}
                  >
                    {col.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {overflowLink}
    </div>
  );
}
