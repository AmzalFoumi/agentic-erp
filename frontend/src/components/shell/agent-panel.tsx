/**
 * The agent region, shipped in its one real state: unavailable.
 *
 * The Claude Design mockup specifies six states (idle, thinking, streaming,
 * tool-call-in-progress, success, refusal) plus this one. Only this one
 * corresponds to something that exists — the agent service is not built.
 * Shipping the other five would be UI for a backend that isn't there, which
 * is exactly what Gate 13's "no disabled affordance" rule forbids elsewhere.
 * This is the one documented exception — see docs/FRONTEND-PLAN.md, "The
 * agent chat surface." The five interactive states are carried forward as a
 * Gate 13g capability item, not implemented here.
 */
export function AgentPanel() {
  return (
    <aside className="flex w-64 shrink-0 flex-col gap-stack border-l border-border bg-card p-section">
      <div className="text-sm font-semibold">Assistant</div>
      <div className="rounded-(--radius) border border-dashed border-border p-3 text-sm text-muted-foreground">
        Assistant unavailable. This isn&rsquo;t connected yet.
      </div>
      <div className="mt-auto pt-stack">
        <input
          disabled
          placeholder="Assistant unavailable"
          className="h-control w-full rounded-(--radius) border border-input bg-card px-3 text-sm text-foreground disabled:cursor-not-allowed disabled:opacity-60"
        />
      </div>
    </aside>
  );
}
