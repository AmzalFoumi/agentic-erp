/**
 * Temporary token preview — the Gate 11/12b acid test.
 *
 * Renders every design token against realistic data so a token that is defined
 * but never wired through `@theme inline` fails visibly here rather than
 * silently in a real screen. Deleted at Gate 13, when real screens replace it.
 *
 * No API calls: fixtures are inline and shaped like the real schema (money as
 * strings, nullable category, `created_by` as the literal "system").
 */

const ROWS = [
  { sku: "SKU-10000", name: "Whole milk 1L", cat: "Dairy", cost: "780.00", sell: "1050.00", qty: 640 },
  { sku: "SKU-10137", name: "Sourdough loaf", cat: "Bakery", cost: "420.50", sell: "560.00", qty: 12 },
  { sku: "SKU-10274", name: "Free-range eggs (12)", cat: null, cost: "1180.00", sell: "1495.00", qty: 6 },
  { sku: "SKU-10411", name: "Canned tomatoes 400g", cat: "Pantry", cost: "186.75", sell: "251.00", qty: 80 },
  { sku: "SKU-10548", name: "Basmati rice 5kg", cat: "Pantry", cost: "4588.00", sell: "5940.25", qty: 0 },
  { sku: "SKU-10685", name: "Olive oil 1L", cat: "Pantry", cost: "3810.00", sell: "5140.00", qty: 340 },
  { sku: "SKU-10822", name: "Cheddar cheese 200g", cat: "Dairy", cost: "666.00", sell: "899.00", qty: 24 },
  { sku: "SKU-10959", name: "Chicken breast 1kg", cat: "Meat", cost: "1401.00", sell: "1841.50", qty: 18 },
];

/**
 * Format a money string for display. Never parses to a number — that is the
 * float64 precision bug DESIGN.md forbids. Groups the integer part by hand.
 */
function money(value: string): string {
  const [whole, fraction = "00"] = value.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `Rs ${grouped}.${fraction.padEnd(2, "0")}`;
}

const SWATCHES = [
  ["background", "bg-background"],
  ["foreground", "bg-foreground"],
  ["card", "bg-card"],
  ["primary", "bg-primary"],
  ["secondary", "bg-secondary"],
  ["muted", "bg-muted"],
  ["accent", "bg-accent"],
  ["destructive", "bg-destructive"],
  ["border", "bg-border"],
  ["ring", "bg-ring"],
] as const;

const STOCK = [
  ["stock-ok", "bg-stock-ok", "bg-stock-ok-surface text-stock-ok"],
  ["stock-low", "bg-stock-low", "bg-stock-low-surface text-stock-low"],
  ["stock-out", "bg-stock-out", "bg-stock-out-surface text-stock-out"],
  ["stock-over", "bg-stock-over", "bg-stock-over-surface text-stock-over"],
] as const;

function ProductTable() {
  return (
    <table className="w-full border border-border bg-card">
      <thead>
        <tr className="bg-muted text-left">
          {["SKU", "Name", "Category", "Cost", "Sell", "Stock"].map((h) => (
            <th
              key={h}
              className="border-b border-border px-cell-x py-cell-y text-xs font-semibold text-muted-foreground last:text-right [&:nth-child(4)]:text-right [&:nth-child(5)]:text-right"
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ROWS.map((r) => (
          <tr key={r.sku} className="h-row border-b border-border last:border-0">
            <td className="px-cell-x py-cell-y font-mono text-xs text-muted-foreground">{r.sku}</td>
            <td className="px-cell-x py-cell-y text-sm">{r.name}</td>
            <td className="px-cell-x py-cell-y text-sm text-muted-foreground">
              {r.cat ?? <span className="italic opacity-60">—</span>}
            </td>
            <td className="px-cell-x py-cell-y text-right font-mono text-xs text-muted-foreground">
              {money(r.cost)}
            </td>
            <td className="px-cell-x py-cell-y text-right font-mono text-xs">{money(r.sell)}</td>
            <td className="px-cell-x py-cell-y text-right font-mono text-xs">
              {r.qty === 0 ? (
                <span className="bg-stock-out-surface px-1.5 py-0.5 font-semibold text-stock-out">
                  {r.qty}
                </span>
              ) : (
                r.qty
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function TokenPreview() {
  return (
    <main className="min-h-screen bg-background p-section text-foreground">
      <div className="mx-auto flex max-w-5xl flex-col gap-section">
        <header>
          <h1 className="text-2xl font-semibold">Token preview</h1>
          <p className="text-sm text-muted-foreground">
            Temporary — deleted at Gate 13. Body text is Figtree; numeric columns are IBM Plex Mono.
          </p>
        </header>

        <section className="flex flex-col gap-stack">
          <h2 className="text-lg font-semibold">Semantic colours</h2>
          <div className="flex flex-wrap gap-stack">
            {SWATCHES.map(([name, cls]) => (
              <div key={name} className="flex flex-col gap-1">
                <div className={`h-12 w-28 border border-border ${cls}`} />
                <span className="font-mono text-xs text-muted-foreground">{name}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-stack">
          <h2 className="text-lg font-semibold">Stock status</h2>
          <div className="flex flex-wrap gap-stack">
            {STOCK.map(([name, solid, badge]) => (
              <div key={name} className="flex flex-col gap-1">
                <div className={`h-12 w-28 border border-border ${solid}`} />
                <span className={`px-1.5 py-0.5 text-center font-mono text-xs font-semibold ${badge}`}>
                  {name}
                </span>
              </div>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-stack" data-density="dense">
          <h2 className="text-lg font-semibold">Product table — dense (default)</h2>
          <ProductTable />
        </section>

        <section className="flex flex-col gap-stack" data-density="comfortable">
          <h2 className="text-lg font-semibold">Product table — comfortable</h2>
          <ProductTable />
        </section>
      </div>
    </main>
  );
}
