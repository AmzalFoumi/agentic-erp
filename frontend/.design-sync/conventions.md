## This is a tokens-only design system — no components yet

There is no component library to import from `window.InventoryDS` (it's
empty). Build screens with your own component vocabulary (shadcn-style
primitives, plain HTML) and style them entirely through the CSS custom
properties below, sourced from `styles.css`. Do not invent new color values,
spacing values, or font names — every value this system needs already has a
token.

## Colors — reference the semantic name, never a raw value

Follow shadcn's naming: `background`, `foreground`, `card`, `primary`,
`secondary`, `muted`, `accent`, `destructive`, `border`, `input`, `ring`,
each with light values under `:root` and dark values under `.dark`. Use them
as `var(--background)`, `var(--primary)`, etc. — never hardcode an OKLCH/hex
value; that breaks re-theming and dark mode.

**`--destructive` is reserved for an irreversible user action** (delete,
discard). It is never a color for "this is bad" facts about data — see stock
status below.

## Stock status — a separate 4-token family, not part of the semantic set

`--stock-ok`, `--stock-low`, `--stock-out`, `--stock-over`, each paired with
a `-surface` variant for badge backgrounds (e.g. `--stock-low-surface`).
Green/amber/red/violet. Low stock is a normal operating condition (amber,
not alarming); only out-of-stock reads as urgent (red). `--stock-over` is a
real, defined token — but nothing in this product uses it yet (no backing
data field). Include it in generated UI only as a passive, unused state, not
as an active feature.

## Density — the load-bearing axis, do not flatten it

Every spacing value used for tables, rows, and controls comes from six
tokens keyed on an HTML attribute, not one fixed scale:

| Token | Use |
|---|---|
| `--cell-x` | horizontal cell padding |
| `--cell-y` | vertical cell padding |
| `--row-h` | table row height |
| `--control-h` | button/input/select height |
| `--stack` | gap between related elements |
| `--section` | gap between unrelated blocks |

These resolve differently depending on `data-density="dense"` (default,
smaller — an operator scanning hundreds of rows) vs.
`data-density="comfortable"` (larger — touch, long sessions) on the `<html>`
element. **Never hardcode a pixel/rem value for row height, cell padding, or
control height** — always reference these tokens, so the density toggle
keeps working. A component that hardcodes `h-8` or `py-2` for a table row
silently breaks the whole feature.

## Type

Two families only: a UI sans and a monospace for numbers (money, quantities,
SKUs) — reference them by the standard `font-sans` / `font-mono` utility,
never introduce a third typeface. Numeric columns use tabular figures
(`font-variant-numeric: tabular-nums`) so digits align down a column — apply
this to any table or numeric cell.

## Where the truth lives

Read `styles.css` (and its `@import` closure, including `_ds_bundle.css`)
for the authoritative token values — this file names them, it never
restates numbers. `DESIGN.md` (bundled alongside) explains the *why* behind
each decision in prose, deliberately with no numbers in it.

## One idiomatic snippet

```tsx
<table>
  <tbody>
    <tr className="h-row">
      <td className="px-cell-x py-cell-y text-right" data-numeric>
        Rs 1,250.00
      </td>
      <td className="px-cell-x py-cell-y">
        <span
          className="rounded px-2 py-0.5"
          style={{
            color: "var(--stock-low)",
            background: "var(--stock-low-surface)",
          }}
        >
          Low stock
        </span>
      </td>
    </tr>
  </tbody>
</table>
```
