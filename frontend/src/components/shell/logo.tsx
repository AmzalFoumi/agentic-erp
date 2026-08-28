import Image from "next/image";
import Link from "next/link";

import { cn } from "@/lib/utils";

/**
 * The "AIsle" wordmark — the product name, replacing the placeholder "Inventory"
 * text in the app header and on the signed-out landing card.
 *
 * Rendered from the designed mark (`public/aisle-wordmark.png`, trimmed from
 * the source `aisle-logo-nobg.png` to its content bounding box so it isn't
 * mostly whitespace) rather than as live CSS text. That trades away automatic
 * dark-mode adaptation — the mark's blue/slate colours are fixed, not theme
 * tokens — for showing the actual designed lettering (straight "AI" +
 * cursive "sle"), which CSS text/fonts alone didn't reproduce.
 *
 * `href={null}` renders the bare mark with no link, for the landing page where
 * every in-app route would just bounce a signed-out visitor back.
 */
export function Logo({
  className,
  href = "/products",
}: {
  className?: string;
  href?: string | null;
}) {
  const wordmark = (
    <Image
      src="/aisle-wordmark.png"
      alt="AIsle"
      width={302}
      height={109}
      priority
      className={cn("h-8 w-auto", className)}
    />
  );

  if (!href) return wordmark;

  return (
    <Link href={href} aria-label="AIsle — go to products" className="inline-flex">
      {wordmark}
    </Link>
  );
}
