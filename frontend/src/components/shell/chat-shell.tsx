"use client";

import type { ReactNode } from "react";

import { AgentPanel } from "./agent-panel";
import { Nav } from "./nav";

/**
 * The signed-in content row: side nav, the page, and the agent panel.
 *
 * Lifted out of layout.tsx (a Server Component) into its own client component
 * so it can own the docked/expanded state that gate 31 adds. `children` is the
 * server-rendered page, passed straight through — a client component rendering
 * server children is the standard App Router pattern and changes nothing about
 * how the page itself renders.
 *
 * Gate 31, task 1: structure only, always docked. Task 2 adds the mode state.
 */
export function ChatShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-1 min-h-0">
      <Nav />
      <main className="flex-1 min-w-0 overflow-auto p-section">{children}</main>
      <AgentPanel />
    </div>
  );
}
