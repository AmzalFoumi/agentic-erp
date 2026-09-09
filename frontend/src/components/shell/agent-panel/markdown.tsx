"use client";

import { Streamdown } from "streamdown";
import type { ComponentProps } from "react";

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
 * override is link colour (to match every other link in the app) and the
 * container type size. No colours, radii or raw lengths live here — see the
 * plan's Global Constraints.
 *
 * Safety: Streamdown's default pipeline (rehype-sanitize + rehype-harden)
 * strips <script>/<iframe>/event handlers and javascript:/data: script URLs;
 * every link it renders already gets rel="noreferrer" target="_blank". We also
 * drop images entirely — the agent answers about internal stock, it has no
 * reason to embed remote media, and an <img> is the one easy exfiltration
 * pixel that survives sanitization.
 *
 * Reused by gate 34's response cards for any model prose inside a card; pass
 * `className` to tighten the spacing there.
 */

const components = {
  a: ({ className, ...props }: ComponentProps<"a"> & { node?: unknown }) => (
    <a
      {...props}
      // target/rel are already set by Streamdown; repeating them is harmless
      // and makes the intent obvious at the call site.
      target="_blank"
      rel="noreferrer"
      className={cn("text-primary hover:underline", className)}
    />
  ),
};

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
        // `max-w-none` because the chat bubble is already the width constraint;
        // Streamdown's default prose max-width would double-constrain it.
        "text-sm leading-relaxed max-w-none",
        className,
      )}
      components={components}
      disallowedElements={["img"]}
      unwrapDisallowed
      caret="block"
      isAnimating={isAnimating}
    >
      {children}
    </Streamdown>
  );
}
