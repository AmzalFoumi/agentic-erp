"use client";

import type { ReactNode } from "react";

import type { ToolUIPart } from "../use-panel-state";
import { CardErrorBoundary } from "./card-error-boundary";
import { FallbackCard } from "./fallback-card";
import { ProductCard, ProductListCard } from "./product-cards";

/**
 * The one place a tool name maps to a card. Every entry is keyed by the wire
 * part type — "tool-<mcp_tool_name>" — so a new backend tool renders through
 * <FallbackCard> until someone deliberately adds a row here. No tool name is
 * hardcoded anywhere else (Global Constraint, see use-panel-state.ts).
 *
 * Populated by the card tasks that follow. Empty here on purpose.
 */
export type ToolCard = (props: { output: unknown }) => ReactNode;

export const CARD_REGISTRY: Record<string, ToolCard> = {
  "tool-list_products": ProductListCard,
  "tool-get_product": ProductCard,
  "tool-get_product_by_sku": ProductCard,
};

/**
 * Render the card for one `output-available` tool part. Read tools have no
 * `approval` object; parts that do (the write-side tools) are handled by the
 * panel's separate approval/success treatment and must not be passed here.
 */
export function renderToolCard(part: ToolUIPart): ReactNode {
  const Card = CARD_REGISTRY[part.type] ?? FallbackCard;
  return (
    <CardErrorBoundary fallback={<FallbackCard output={part.output} />}>
      <Card output={part.output} />
    </CardErrorBoundary>
  );
}
