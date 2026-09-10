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

export const checkSpoilageRiskFixture: MCPToolOutputs["check_spoilage_risk"] = {
  scanned_on: "2026-09-10",
  within_days: 7,
  total_cost_at_risk: "4560.00",
  total_projected_recovery: "2280.00",
  items: [
    {
      lot_id: 12,
      product_id: 1,
      sku: "2002-1001",
      product_name: "Full Cream Milk 1L",
      lot_code: "L-2609-A",
      expiry_date: "2026-09-14",
      days_remaining: 4,
      quantity: 18,
      current_price: "420.50",
      proposed_price: "294.35",
      discount_percent: 30,
      why: "Expires within the markdown window",
      cost_at_risk: "6840.00",
      projected_recovery: "5298.30",
    },
  ],
};

export const listProductLotsFixture: MCPToolOutputs["list_product_lots"] = {
  lots: [
    {
      lot_id: 12,
      product_id: 1,
      lot_code: "L-2609-A",
      expiry_date: "2026-09-14",
      quantity: 18,
      cost_price: "380.00",
      sell_price: "420.50",
      discount_percent: 0,
      is_expired: false,
    },
    {
      lot_id: 9,
      product_id: 1,
      lot_code: "L-2608-B",
      expiry_date: null,
      quantity: 6,
      cost_price: "375.00",
      sell_price: "420.50",
      discount_percent: 0,
      is_expired: false,
    },
  ],
};

export const suggestReorderBundlesFixture: MCPToolOutputs["suggest_reorder_bundles"] = {
  total_value: "18400.00",
  bundles: [
    {
      supplier_id: 3,
      supplier_name: "Highland Dairy Co.",
      lead_time_days: 2,
      minimum_order_value: "10000.00",
      bundle_value: "12600.00",
      below_minimum: false,
      shortfall: "0.00",
      lines: [
        {
          product_id: 1,
          sku: "2002-1001",
          name: "Full Cream Milk 1L",
          quantity_on_hand: 6,
          reorder_level: 24,
          quantity: 48,
          unit_cost: "262.50",
          pack_size: 12,
          line_total: "12600.00",
          is_top_up: false,
        },
      ],
    },
  ],
  unsourced: [
    {
      product_id: 7,
      sku: "3001-2002",
      name: "House Blend Coffee 250g",
      quantity_on_hand: 2,
      reorder_level: 10,
    },
  ],
};

export const listPendingDraftsFixture: MCPToolOutputs["list_pending_drafts"] = {
  drafts: [
    {
      id: 41,
      draft_type: "SUPPLIER_REORDER",
      status: "PENDING",
      payload: {
        supplier_id: 3,
        expected_date: "2026-09-15",
        lines: [{ product_id: 1, quantity: 48, unit_cost: "262.50" }],
      },
      reasoning: "Milk is below reorder level with a 2-day lead time.",
      cost_at_risk: null,
      projected_recovery: null,
      expires_at: "2026-09-12",
      is_expired: false,
      created_by: "01a02d8f-1111-2222-3333-444455556666",
      created_via: "agent",
      decided_by: null,
      decided_via: null,
    },
  ],
};

export const listPurchaseOrdersFixture: MCPToolOutputs["list_purchase_orders"] = {
  total: 1,
  orders: [
    {
      id: 12,
      supplier_id: 3,
      status: "PLACED",
      expected_date: "2026-09-15",
      total_value: "12600.00",
      notes: null,
      source_draft_id: 41,
      created_by: "01a02d8f-1111-2222-3333-444455556666",
      lines: [
        { product_id: 1, quantity_ordered: 48, unit_cost: "262.50", line_total: "12600.00" },
      ],
    },
  ],
};
