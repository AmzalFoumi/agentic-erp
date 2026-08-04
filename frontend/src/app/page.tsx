import { redirect } from "next/navigation";

/**
 * No dashboard — the nav has exactly two destinations (see shell/nav.tsx),
 * so "/" has nothing of its own to show. Products is where anyone lands.
 */
export default function Home() {
  redirect("/products");
}
