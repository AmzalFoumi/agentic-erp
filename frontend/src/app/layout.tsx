import type { Metadata } from "next";
import { Figtree, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

import { ThunderIDProvider } from "@thunderid/nextjs/server";

import { AgentPanel } from "@/components/shell/agent-panel";
import { DensityToggle } from "@/components/shell/density-toggle";
import { Nav } from "@/components/shell/nav";
import { ThemeProvider } from "@/components/shell/theme-provider";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { UserMenu } from "@/components/shell/user-menu";
import { SignedIn, SignedOut } from "@thunderid/nextjs";

/*
 * The design system specifies Figtree for UI and IBM Plex Mono for data. It
 * delivered them as an @import from fonts.googleapis.com, which is not shippable
 * here: a runtime @import is a render-blocking round trip on every load and
 * discloses every visitor's IP to a third party. next/font downloads at build
 * time and self-hosts, so the same typefaces cost nothing at runtime.
 *
 * IBM Plex Mono carries the numeric columns — money, quantities, SKUs — where
 * fixed-width digits are the point rather than a stylistic preference.
 */
const fontSans = Figtree({
  variable: "--font-app-sans",
  subsets: ["latin"],
});

const fontMono = IBM_Plex_Mono({
  variable: "--font-app-mono",
  weight: ["400", "500", "600"],
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Inventory",
  description: "Supermarket inventory and purchasing",
};

/**
 * Every route is rendered per request, never prerendered at build time.
 *
 * **This is required for `next build` to succeed at all**, and it was found by
 * gate 26 — the first time this app had ever been built for production rather
 * than run with `next dev`.
 *
 * Next decides statically-renderable pages by *trying* to prerender them and
 * treating its own `DynamicServerError` ("this route used `headers`") as the
 * signal to fall back to per-request rendering. `ThunderIDProvider` below reads
 * headers, so that signal fires on every route — but the SDK catches it and
 * rethrows it as a fatal `ThunderIDRuntimeError`, which Next cannot recognise.
 * The build then dies on `/` with "Export encountered an error". Checked
 * against @thunderid/nextjs 1.0.6 on 2026-08-26.
 *
 * Declaring it here states the truth rather than working around it: nothing in
 * Aisle is prerenderable. Every screen needs a session and live data, and `/`
 * itself renders differently signed in and signed out.
 *
 * Still supported in Next 16 (removed only when `cacheComponents` is enabled,
 * which this project does not enable) — see
 * `node_modules/next/dist/docs/01-app/02-guides/caching-without-cache-components.md`.
 */
export const dynamic = "force-dynamic";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // `data-density` is server-rendered as the default rather than applied by
    // an effect, so the first paint is already at the right row height. A
    // client toggle can overwrite the attribute later; nothing else changes.
    // See frontend/DESIGN.md.
    // suppressHydrationWarning is next-themes' documented requirement on
    // <html>: it sets the `.dark` class from an inline script before React
    // hydrates, which is an intentional, expected mismatch React would
    // otherwise warn about.
    <html
      lang="en"
      data-density="dense"
      className={`${fontSans.variable} ${fontMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="flex h-screen flex-col overflow-hidden">
        {/*
          ThunderIDProvider is imported from the `/server` subpath, not the
          package root — it is an async Server Component that resolves the
          session, the user profile and the flow metadata on the server and
          seeds the client context with them. That is why `SignedIn` /
          `SignedOut` below do not flash the wrong branch on first paint:
          `isSignedIn` arrives already decided, not discovered after hydration.

          It is configured entirely from environment variables rather than
          props (see frontend/.env.example). One sharp edge worth knowing: if
          the client fails to initialise, the provider renders *nothing* — a
          blank page rather than an error — so a completely empty app is a
          configuration problem, not a routing one.

          Outside ThemeProvider so the whole tree, sign-in page included, is
          inside both.
        */}
        <ThunderIDProvider>
          <ThemeProvider>
            {/*
              The shell is for people who are signed in. `/` renders bare when
              they are not, and not only for looks: AgentPanel starts a
              conversation against /api/agent on mount, and that route is
              protected by src/proxy.ts, so mounting it on the signed-out
              landing would fire a request that gets redirected straight back.

              Every other route is protected, so in practice the SignedOut
              branch only ever renders `/` (see app/page.tsx, and the note in
              src/proxy.ts on why `/` cannot itself be protected).
            */}
            <SignedIn>
              {/* App header */}
              <div className="flex items-center justify-between border-b border-border bg-card px-5 py-3">
                <div className="text-sm font-semibold">Inventory</div>
                <div className="flex items-center gap-4">
                  <DensityToggle />
                  <ThemeToggle />
                  <UserMenu />
                </div>
              </div>

              <div className="flex flex-1 min-h-0">
                <Nav />
                <main className="flex-1 min-w-0 overflow-auto p-section">
                  {children}
                </main>
                <AgentPanel />
              </div>
            </SignedIn>

            <SignedOut>
              <main className="flex flex-1 items-center justify-center overflow-auto p-section">
                {children}
              </main>
            </SignedOut>
          </ThemeProvider>
        </ThunderIDProvider>
      </body>
    </html>
  );
}
