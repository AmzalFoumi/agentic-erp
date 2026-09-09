"use client";

import { Streamdown } from "streamdown";

import { cn } from "@/lib/utils";

/**
 * Markdown rendering for assistant prose. Gate 32.
 *
 * Wraps Streamdown (a streaming-hardened drop-in for react-markdown): it parses
 * incomplete Markdown without crashing — a half-streamed ``` fence or | table |
 * renders as far as it got and completes itself as more tokens arrive.
 *
 * Styling: Streamdown's built-in classes read the same shadcn CSS variables
 * this project maps in globals.css (--foreground, --primary, --border,
 * --radius, --muted...), so headings, lists, tables, blockquotes and code
 * inherit the design system, dark mode, and both densities for free. The only
 * addition is the link colour, applied as a descendant utility on the root so
 * it matches every other link in the app without a custom element renderer.
 * No colours, radii or raw lengths live here — see the plan's Global
 * Constraints. Streamdown already renders links with
 * rel="noreferrer" target="_blank", so nothing here needs to.
 *
 * Safety: Streamdown's default pipeline (rehype-sanitize + rehype-harden)
 * strips <script>/<iframe>/event handlers and javascript:/data: script URLs.
 * We also drop images entirely — the agent answers about internal stock, it
 * has no reason to embed remote media, and an <img> is the one easy
 * exfiltration pixel that survives sanitization.
 *
 * Reused by gate 34's response cards for any model prose inside a card; pass
 * `className` to tighten the spacing there.
 */
export function Markdown({
  children,
  className,
  isAnimating,
}: {
  children: string;
  className?: string;
  isAnimating?: boolean;
}) {
  return (
    <Streamdown
      className={cn(
        // `text-sm` is repeated from the chat bubble on purpose: gate 34
        // renders <Markdown> inside cards that have no bubble around them.
        // `max-w-none` because the bubble is already the width constraint;
        // Streamdown's default prose max-width would double-constrain it.
        "text-sm leading-relaxed max-w-none",
        "[&_a]:text-primary [&_a:hover]:underline",
        className,
      )}
      disallowedElements={["img"]}
      unwrapDisallowed
      caret="block"
      isAnimating={isAnimating}
    >
      {children}
    </Streamdown>
  );
}
