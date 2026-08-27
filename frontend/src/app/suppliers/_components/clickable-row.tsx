"use client";

import { useRouter } from "next/navigation";

import { TableRow } from "@/components/ui/table";

/**
 * The design makes an entire row navigate to detail. A <tr> can't be
 * wrapped in a real <Link> without breaking table semantics, so this is a
 * client component doing `router.push` — the smallest boundary that gets
 * the interaction without turning the whole list client-side.
 *
 * Same component as products/_components/clickable-row.tsx. Not shared
 * across route segments — each `_components` folder is private to its own
 * route by Next.js convention, so it is copied rather than imported.
 */
export function ClickableRow({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  return (
    <TableRow
      role="link"
      tabIndex={0}
      onClick={() => router.push(href)}
      onKeyDown={(e) => {
        // `currentTarget` is the row; `target` is whatever actually had focus.
        // Without this check, Enter on the nested Deactivate button would
        // deactivate the supplier *and* navigate away from the list. A click
        // on that button is already stopped by the button itself.
        if (e.key === "Enter" && e.target === e.currentTarget) router.push(href);
      }}
      className="h-row cursor-pointer"
    >
      {children}
    </TableRow>
  );
}
