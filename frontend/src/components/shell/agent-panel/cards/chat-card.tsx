"use client";

import type { ReactNode } from "react";

/**
 * The shared shell for every response card (read-side cards, and — after the
 * restyle task — the approval and success cards too). One border, one surface,
 * one title treatment, so the chat reads as one system rather than a pile of
 * differently-drawn boxes.
 *
 * No colours, radii, or lengths live here beyond token utilities — see the
 * plan's Global Constraints.
 */
export function ChatCard({
  title,
  headerRight,
  children,
}: {
  title: string;
  headerRight?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-(--radius) border border-border bg-card p-3 text-sm">
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-xs font-semibold uppercase text-muted-foreground">{title}</div>
        {headerRight != null && (
          <div className="shrink-0 text-xs text-muted-foreground tabular-nums">{headerRight}</div>
        )}
      </div>
      {children}
    </div>
  );
}
