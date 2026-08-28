"use server";

/**
 * Send / cancel a purchase order.
 *
 * Server Actions, not a route under `app/api` — same reasoning as everywhere
 * else in this app. Neither of these decides anything: the backend's own
 * state machine (services/purchasing/orders.py::LEGAL_TRANSITIONS) is the
 * only place that transition is enforced, and it refuses illegally even if
 * this page's disabled buttons are somehow bypassed.
 */

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/client";

export type OrderActionResult = { error: string } | null;

type ReceiptLineCreate = components["schemas"]["ReceiptLineCreate"];

export async function sendOrder(orderId: number): Promise<OrderActionResult> {
  const { error } = await api.POST("/purchase-orders/{order_id}/send", {
    params: { path: { order_id: orderId } },
  });

  if (error) {
    return { error: error.detail };
  }

  revalidatePath(`/purchasing/orders/${orderId}`);
  revalidatePath("/purchasing/orders");
  return null;
}

export async function receiveOrder(
  orderId: number,
  lines: ReceiptLineCreate[],
): Promise<OrderActionResult> {
  const { error } = await api.POST("/purchase-orders/{order_id}/receive", {
    params: { path: { order_id: orderId } },
    body: { lines },
  });

  if (error) {
    return { error: error.detail };
  }

  revalidatePath(`/purchasing/orders/${orderId}`);
  revalidatePath("/purchasing/orders");
  return null;
}

export async function cancelOrder(orderId: number): Promise<OrderActionResult> {
  const { error } = await api.POST("/purchase-orders/{order_id}/cancel", {
    params: { path: { order_id: orderId } },
  });

  if (error) {
    return { error: error.detail };
  }

  revalidatePath(`/purchasing/orders/${orderId}`);
  revalidatePath("/purchasing/orders");
  return null;
}
