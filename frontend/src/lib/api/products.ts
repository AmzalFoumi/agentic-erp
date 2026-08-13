"use server";

/**
 * The one thing a client component (the agent panel's approval card) needs
 * from the products API: resolving a bare `product_id` to something a human
 * recognizes. A Server Action, not a new `app/api` route — it's a plain
 * function a client component can call directly, runs on the server so it
 * can use the `server-only` typed client below, and doesn't add a second
 * HTTP surface mirroring FastAPI.
 */
import { api } from "./client";

export async function getProductSummary(
  productId: number,
): Promise<{ sku: string; name: string } | null> {
  const { data, error } = await api.GET("/products/{product_id}", {
    params: { path: { product_id: productId } },
  });
  if (error || !data) {
    return null;
  }
  return { sku: data.sku, name: data.name };
}
