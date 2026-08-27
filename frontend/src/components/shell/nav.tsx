"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const links = [
  { href: "/products", label: "Products" },
  { href: "/products/new", label: "New product" },
  { href: "/inventory/spoilage", label: "Expiring soon" },
  { href: "/approvals", label: "Approvals" },
];

/**
 * Three destinations, deliberately — see the capability inventory in
 * docs/FRONTEND-PLAN.md. No dashboard, no reports, no settings.
 *
 * "Expiring soon" arrived with gate 28. It sits directly above Approvals
 * because that is the order the work happens in: look at what is spoiling,
 * stage a markdown, then approve it. A manager following the feature top to
 * bottom is following the nav.
 *
 * "Approvals" arrived with gate 27 and is the one screen that is not about
 * products: it is where changes the assistant has proposed wait for a human.
 * It earns top-level placement because a proposal nobody notices is a proposal
 * that expires, and the queue is the only thing standing between the agent and
 * an unsupervised write.
 */
export function Nav() {
  const pathname = usePathname();

  return (
    <nav className="flex w-48 shrink-0 flex-col gap-stack border-r border-border bg-sidebar px-3 py-section">
      {links.map((link) => {
        // "/products" must not stay highlighted while on "/products/new".
        const active =
          link.href === "/products"
            ? pathname === "/products" || /^\/products\/\d+/.test(pathname)
            : pathname.startsWith(link.href);

        return (
          <Link
            key={link.href}
            href={link.href}
            className={cn(
              "rounded-(--radius) px-3 text-left text-sm h-control flex items-center",
              active
                ? "bg-secondary font-medium text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
