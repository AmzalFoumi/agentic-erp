import { PackageSearch, TriangleAlert, Truck } from "lucide-react";

import { SignInButton, SignedIn, SignedOut } from "@thunderid/nextjs";

import { AfterSignInRedirect } from "@/components/shell/after-sign-in-redirect";
import { Logo } from "@/components/shell/logo";

/**
 * The signed-out landing page, and the only route the app serves that is not
 * behind `src/proxy.ts`.
 *
 * It has to be public, and for a mechanical reason rather than a product one.
 * `thunderid.protectRoute()` redirects an unauthenticated visitor to
 * `config.signInUrl ?? "/"` — and in ThunderID-hosted ("Gate") mode
 * `NEXT_PUBLIC_THUNDERID_SIGN_IN_URL` is deliberately unset, so that fallback
 * is `/`. Protecting `/` would therefore redirect `/` to itself. See
 * `node_modules/@thunderid/nextjs/dist/server/proxy/thunderIDProxy.js`.
 *
 * So every protected route funnels a signed-out visitor here, and here is the
 * only way out again: every button below is a `<SignInButton>`, never a link
 * to a separate sign-in screen — there isn't one. `<SignInButton>` calls the
 * `signIn` server action with an empty payload, which returns ThunderID's
 * authorize URL and hands the browser over to the hosted sign-in page. On the
 * way back the provider in `layout.tsx` reads `code`/`state` off the URL and
 * completes the exchange — which is why the Authorized Redirect URI
 * registered in the Console is the bare origin, with no callback path.
 *
 * Because `/` is also that callback URL, this route serves two audiences.
 * Signed out it is the marketing page below; signed in it forwards to the
 * product list via `AfterSignInRedirect`, which is where the old
 * `redirect("/products")` went.
 * That forwarding cannot be `NEXT_PUBLIC_THUNDERID_AFTER_SIGN_IN_URL`: see the
 * note on that variable in .env.example.
 */
export default function Home() {
  return (
    <>
      <SignedIn>
        <AfterSignInRedirect />
      </SignedIn>

      <SignedOut>
        <div className="flex flex-col">
          {/* Header */}
          <header className="sticky top-0 z-10 border-b border-border bg-background/95 backdrop-blur">
            <div className="mx-auto flex h-row max-w-6xl items-center justify-between px-cell-x">
              <Logo href={null} className="h-6" />
              <SignInButton className="h-control rounded-(--radius) px-4 text-sm font-medium text-primary hover:bg-accent">
                Sign in
              </SignInButton>
            </div>
          </header>

          <main className="mx-auto flex w-full max-w-6xl flex-col gap-section px-cell-x py-section">
            {/* Hero */}
            <section className="grid grid-cols-1 items-center gap-section py-section md:grid-cols-2 md:py-16">
              <div className="flex flex-col gap-stack">
                <h1 className="text-4xl font-bold tracking-tight text-foreground md:text-5xl">
                  Supermarket operations,{" "}
                  <span className="text-primary">automated.</span>
                </h1>
                <p className="max-w-prose text-lg text-muted-foreground">
                  AIsle is your agentic AI co-pilot for high-velocity inventory
                  management — checking stock, flagging spoilage, and drafting
                  reorders, with a human approving every change.
                </p>
                <div className="mt-2 flex gap-stack">
                  <SignInButton className="h-control rounded-(--radius) bg-primary px-6 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90">
                    Get started
                  </SignInButton>
                </div>
              </div>

              {/*
                No stock photography here on purpose — Aisle has no marketing
                shoot, and a fabricated "supermarket aisle" photo would
                misrepresent the product. This mock panel is built from the
                same design tokens as the real product list / stock badges
                (see docs/FRONTEND-PLAN.md), so what a signed-out visitor sees
                is an honest preview of the actual UI, not a stand-in for it.
              */}
              <div className="rounded-xl border border-border bg-card p-section shadow-sm">
                <div className="mb-stack flex items-center justify-between">
                  <span className="font-mono text-sm text-muted-foreground">
                    Products
                  </span>
                  <span className="rounded-(--radius) bg-stock-low-surface px-2 py-0.5 text-xs font-medium text-stock-low">
                    3 low
                  </span>
                </div>
                <div className="flex flex-col gap-2">
                  {[
                    { name: "Whole milk, 1L", qty: "142 units", tone: "ok" as const },
                    { name: "Sourdough loaf", qty: "6 units", tone: "low" as const },
                    { name: "Cage-free eggs, 12ct", qty: "0 units", tone: "out" as const },
                  ].map((row) => (
                    <div
                      key={row.name}
                      className="flex items-center justify-between rounded-(--radius) border border-border bg-background px-cell-x py-cell-y"
                    >
                      <span className="text-sm text-foreground">{row.name}</span>
                      <span
                        className={
                          "font-mono text-xs " +
                          (row.tone === "ok"
                            ? "text-stock-ok"
                            : row.tone === "low"
                              ? "text-stock-low"
                              : "text-stock-out")
                        }
                      >
                        {row.qty}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            {/* Value proposition */}
            <section className="flex flex-col gap-section py-section">
              <div className="mx-auto max-w-2xl text-center">
                <h2 className="text-2xl font-semibold text-foreground">
                  Built for operators, not spreadsheets
                </h2>
                <p className="mt-2 text-muted-foreground">
                  Designed for teams who track thousands of SKUs daily. Aisle
                  replaces guesswork with fact-based tracking, and never acts
                  without a human in the loop.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-section md:grid-cols-3">
                <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-section shadow-sm">
                  <div className="mb-1 flex h-10 w-10 items-center justify-center rounded-full bg-stock-ok-surface text-stock-ok">
                    <PackageSearch className="h-5 w-5" />
                  </div>
                  <h3 className="font-semibold text-foreground">Check stock</h3>
                  <p className="text-sm text-muted-foreground">
                    Real-time visibility into what&apos;s on the shelf, so
                    system records match physical reality.
                  </p>
                </div>

                <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-section shadow-sm">
                  <div className="mb-1 flex h-10 w-10 items-center justify-center rounded-full bg-stock-out-surface text-stock-out">
                    <TriangleAlert className="h-5 w-5" />
                  </div>
                  <h3 className="font-semibold text-foreground">Flag spoilage</h3>
                  <p className="text-sm text-muted-foreground">
                    Catch compromised lots before they reach a customer, with
                    every write-off logged and accountable.
                  </p>
                </div>

                <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-section shadow-sm">
                  <div className="mb-1 flex h-10 w-10 items-center justify-center rounded-full bg-stock-low-surface text-stock-low">
                    <Truck className="h-5 w-5" />
                  </div>
                  <h3 className="font-semibold text-foreground">Handle reordering</h3>
                  <p className="text-sm text-muted-foreground">
                    The agent drafts reorder manifests from velocity and lead
                    times. You review and approve — it never decides alone.
                  </p>
                </div>
              </div>
            </section>

            {/* CTA */}
            <section className="rounded-xl border border-border bg-muted p-section text-center md:p-12">
              <h2 className="text-2xl font-semibold text-foreground">
                Ready to optimize your aisles?
              </h2>
              <p className="mx-auto mt-2 max-w-xl text-muted-foreground">
                Sign in with your ThunderID account to get started.
              </p>
              <SignInButton className="mt-6 h-control rounded-(--radius) bg-primary px-6 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90">
                Sign in
              </SignInButton>
            </section>
          </main>

          <footer className="border-t border-border py-section">
            <div className="mx-auto flex max-w-6xl items-center justify-between px-cell-x text-sm text-muted-foreground">
              <Logo href={null} className="h-4 opacity-70 grayscale" />
              <span>© 2026 Aisle</span>
            </div>
          </footer>
        </div>
      </SignedOut>
    </>
  );
}
