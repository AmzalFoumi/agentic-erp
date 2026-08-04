# DESIGN.md — the design system, in words

> **This file never contains a hex, an rem, an OKLCH triple, or a ratio.**
> Every value lives in exactly one place: the `@theme` and token blocks in
> `src/app/globals.css`. This file names the tokens and explains why they exist.

Two files that must agree by hand are a drift machine — the same failure this project avoids at the
code level with `lint-imports` and a generated API client. If you find yourself wanting to write a
number here, the honest move is a comment in `globals.css` instead.

Scope: this is the design system. What the screens *are* is `docs/FRONTEND-PLAN.md`; what the API can
actually do is that file's capability inventory, which outranks anything a design suggests.

---

## Colour

shadcn's semantic token set, in OKLCH, mapped through `@theme inline` onto `:root` and `.dark`.
Components reference the semantic name — `bg-card`, `text-muted-foreground`, `border-border` — and
never a palette step. That indirection is the whole point: retheming is editing one block, not
grepping the component tree.

**The concrete palette is supplied by the developer, not invented here.** This file defines the
*slots*; the values arrive via Claude Design and get synced into `globals.css`. The named failure
mode is the generic AI aesthetic — the same gradients and the same soft rounded cards on every recent
site — and the way to avoid it is to have a human supply real brand input, not to have the agent try
harder.

Note that Claude Design *generates* a system from what it is given rather than offering themes to
browse, so the quality of the result is set by the quality of the inspiration uploaded first. The
current greys are shadcn defaults and a placeholder, not a decision — until this paragraph says
otherwise, nothing has chosen them. See `docs/FRONTEND-PLAN.md`, Gate 11.

`--destructive` is the only shadcn colour with a fixed meaning: an irreversible action the user is
about to take. **It is not the colour of out-of-stock.** Destructive is about intent; stock status is
a fact about the world. Sharing the token would make "delete this" and "we sold out" read as the same
kind of event.

### Stock status — four states, added alongside shadcn's set

`stock-ok`, `stock-low`, `stock-out`, `stock-over`, each with a matching `-surface` for badge
backgrounds. Green, amber, red, violet.

Low stock is a **normal operating condition** and gets a warning treatment, not an alarm — if every
row is red, nothing is. Only `stock-out` reads as urgent, because only that one means a customer is
standing in front of an empty shelf.

> **These four states need a threshold the API does not have yet.** "Low" and "over" are meaningless
> without a per-product reorder level and maximum. The design defines them anyway — deliberately, as
> a decision — and the backend work is recorded in `docs/PLAN.md`. Until that field exists, screens
> render `stock-ok` and `stock-out` only; `stock-low` and `stock-over` are defined, unused, and
> visible in the design as what the data is missing rather than as a hardcoded guess.

The hardcoded `qty <= 12` in the imported design's test page is exactly the failure this rule
prevents: a threshold invented in a stylesheet, applying equally to milk and to rice.

---

## Type

**Figtree** for UI, **IBM Plex Mono** for numeric columns — money, quantities, SKUs — where
fixed-width digits are the point rather than a preference. Both SIL OFL 1.1, both loaded through
`next/font` and self-hosted rather than fetched from Google at runtime.

Self-hosting means the build redistributes the font files, which carries an attribution obligation.
See [`THIRD-PARTY.md`](./THIRD-PARTY.md) — that file is load-bearing, not boilerplate.

The design system delivered a **px** type scale. It was not adopted: px ignores the reader's browser
font size, which is a real accessibility regression on a screen someone reads for hours. Tailwind's
rem scale stays.

---

## Density

`data-density="dense" | "comfortable"` on `<html>`, composing with `.dark` exactly as shadcn's
theming does. **Dense is the default**, server-rendered in `app/layout.tsx` so first paint is already
at the right row height.

This is an operational tool for someone scanning hundreds of stock rows, not a marketing page. A
comfortable-by-default table shows perhaps twelve rows on a laptop; dense shows twice that, and for
this user "how much can I see at once" is the whole job. Comfortable exists for touch and for long
sessions, and is user-facing.

It is an axis from the start rather than a later addition because retrofitting it means touching
every component that ever hardcoded a padding. The rule that keeps it working:

> **Components reference density tokens. No component hardcodes padding, gap, or row height.**

The tokens, all in Tailwind's `--spacing` namespace so they generate the whole sizing family
(`p-cell-x`, `h-row`, `gap-stack`, …):

| Token | What it is for |
|---|---|
| `cell-x` | Horizontal padding inside a table cell |
| `cell-y` | Vertical padding inside a table cell |
| `row` | Table row height — the number that decides how much fits on screen |
| `control` | Height of a button, input, or select, so controls line up with rows |
| `stack` | Gap between related elements — fields in a form, items in a list |
| `section` | Gap between unrelated blocks on a page |

There is also a `comfortable:` variant for the rare component needing a *structural* change rather
than a different value. Prefer the tokens; a component reading `h-row` needs no variant at all.

---

## Numerals

Money and quantity columns are read **down**, not across. Proportional digits let the ones column
wander between rows and defeat that, so tabular figures are applied in `@layer base` to tables and to
anything marked `data-numeric`, rather than left to each screen to remember.

---

## Money — LKR

ISO 4217 `LKR`, numeric 144, two decimal places. Display as `Rs 1,250.00`, with `en-LK` grouping.

Cents are effectively out of circulation in Sri Lanka, but the column is `Numeric(10,2)` and the API
sends two decimals. **Display both anyway.** An ERP that hides cents while storing them produces
on-screen totals that visibly do not add up, and the person who notices will be right.

> **Hard rule: never call `Intl.NumberFormat` with `style: "currency"` on a `number`.**
>
> Doing so requires `parseFloat` on the wire value, which reintroduces exactly the float64 precision
> bug the string encoding exists to prevent — `"18.00"` becomes `17.999999999999996`. The API
> deliberately serialises money as a JSON **string**; format the string directly, or use a decimal
> library. See the money-as-string rationale in `docs/BACKEND-PLAN.md` and the comment in
> `backend/api/schemas.py`.

Money is right-aligned. Everything else in a table is left-aligned.

---

## Timestamps

The API sends `TIMESTAMPTZ` as ISO 8601 with an offset. Decided once, here, because otherwise four
screens grow four implementations:

- **Displayed in `Asia/Colombo`**, not the browser's zone. Single-location business; a timestamp that
  changes meaning when the laptop travels is worse than one that is always store time.
- **Absolute, not relative.** "3 hours ago" is unusable for reconciling a delivery against a paper
  invoice. Absolute times are also stable across a re-render.
- **Date alone** where the time carries no information (a report period); **date and time to the
  minute** on audit-ish fields like `created_at`. Seconds are never shown.

---

## Components

Gate 11 ships **primitives only** — shadcn defaults bound to the tokens above.

No domain components yet (`MoneyDisplay`, `StockBadge`, `ErrorSurface`). They are opinions about
screens that do not exist, and pre-empting them means reconciling two component kits at Gate 13.
They arrive once the designs do, named after what they mean rather than what they look like.

---

## Attribution

`created_by` and `updated_by` are the literal string `"system"` today, because `SystemActor` is the
only actor that exists — see the auth deferral in `docs/PLAN.md`. **Design for that ugly string.** A
mock showing "Sarah Chen" with an avatar designs a feature the system does not have, and the gap gets
discovered during the build rather than during the design.
