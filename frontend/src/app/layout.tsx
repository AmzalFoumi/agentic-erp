import type { Metadata } from "next";
import { Figtree, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

import { AgentPanel } from "@/components/shell/agent-panel";
import { DensityToggle } from "@/components/shell/density-toggle";
import { Nav } from "@/components/shell/nav";
import { ThemeToggle } from "@/components/shell/theme-toggle";

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
    <html
      lang="en"
      data-density="dense"
      className={`${fontSans.variable} ${fontMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* App header */}
        <div className="flex items-center justify-between border-b border-border bg-card px-5 py-3">
          <div className="text-sm font-semibold">Inventory</div>
          <div className="flex items-center gap-4">
            <DensityToggle />
            <ThemeToggle />
          </div>
        </div>

        <div className="flex flex-1 min-h-0">
          <Nav />
          <main className="flex-1 min-w-0 overflow-auto p-section">
            {children}
          </main>
          <AgentPanel />
        </div>
      </body>
    </html>
  );
}
