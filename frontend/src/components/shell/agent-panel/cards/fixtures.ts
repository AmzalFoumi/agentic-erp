/**
 * Typed sample payloads, one per registered card. Nothing imports these at
 * runtime — `tsc --noEmit` type-checks them against the generated
 * MCPToolOutputs contract, which is the shape guarantee this repo has instead
 * of a card test runner. They are also paste-ready for eyeballing a card
 * during the browser walkthrough.
 */
import type { MCPToolOutputs } from "@/lib/api/mcp-types";

export const listProductsFixture: MCPToolOutputs["list_products"] = {
  total: 2,
  products: [
    {
      id: 1,
      sku: "2002-1001",
      name: "Full Cream Milk 1L",
      category: "Dairy",
      unit: "bottle",
      cost_price: "380.00",
      sell_price: "420.50",
      quantity_on_hand: 48,
      reorder_level: 24,
      needs_reorder: false,
      updated_by: "api",
    },
    {
      id: 2,
      sku: "2002-1002",
      name: "Sparkling Water 1.5L",
      category: "Beverages",
      unit: "bottle",
      cost_price: "150.00",
      sell_price: "190.00",
      quantity_on_hand: 0,
      reorder_level: 24,
      needs_reorder: true,
      updated_by: "mcp",
    },
  ],
};

export const getProductFixture: MCPToolOutputs["get_product"] = listProductsFixture.products[0];
