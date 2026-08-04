# design-sync notes — agentic-erp frontend

## Project history

First sync (2026-08-04) initially uploaded successfully to a reused project
named "Design System" (`a63b6aac-7445-408d-9543-ee1f02a1824d`) — the upload
itself was mechanically sound (`list_files` showed all 24 content files plus
server-generated `_ds_manifest.json`/`_adherence.oxlintrc.json`), but that
project turned out to be gated behind an unfinished onboarding wizard
("Set up your design system") left over from whatever session originally
created it, so it never rendered the synced content. Resolved by creating a
fresh project, **"agentic-erp frontend"**
(`77b1dcd6-d0dc-453a-84a4-c8124bd8547f` — see `config.json`), re-running the
same upload sequence against it, and confirming it opens correctly (Design
System pane, no onboarding gate). The old project has since been deleted by
the user from the claude.ai/design UI. **This is the project all future
`/design-sync` re-syncs should target** — `config.json`'s `projectId` is
already pointed at it.

## Scope for this sync (confirmed with user, 2026-08-04)

Tokens + fonts + `DESIGN.md` as system-level context only. **No components** —
`src/components/ui/` has exactly one file (`button.tsx`), and per
`docs/FRONTEND-PLAN.md` / `DESIGN.md` domain components are deliberately
deferred to Gate 13 (extracted *from* generated designs, not seeded *into*
them). Button will be added once Gate 13 produces more components to sync
alongside it — don't add it back solo without checking with the user first.

This repo is not a publishable component package — it's the Next.js app
itself. `.design-sync/entry.js` is a synthetic zero-export entry so the
converter's package-build pipeline can run in its documented tokens-only mode
("Tokens-only DS (no components): emits styles.css only with an
empty-bodied `_ds_bundle.js`" — non-storybook/SKILL.md, Known limitations).

## Source of truth

- `src/app/globals.css` — the only file with real token values (colors,
  radius, the two density scales + `:root` fallback, stock-status tokens).
  `DESIGN.md` deliberately contains no hex/rem/ratio — don't try to
  cross-check numbers against it.
- `src/app/layout.tsx` — font wiring (`next/font`) and `data-density="dense"`
  set server-side on `<html>`.
- `DESIGN.md` — prose context, included as-is.

## Excluded (confirmed with user)

- `src/app/dev-tokens/` — temporary token-preview page, deleted at Gate 13,
  fake fixture data, not a layout decision.
- `src/lib/**` — API client / generated types, no styling.
- Everything outside `frontend/` (`backend/` holds live DB credentials).
- `src/components/ui/button.tsx` — deferred, see Scope above.

## Load-bearing things to verify post-build, not just trust

1. **Density axis must survive as two live attribute-keyed token sets**,
   not collapse to one resolved scale. `globals.css` has
   `[data-density="dense"]`, `[data-density="comfortable"]`, and a `:root`
   fallback duplicating dense — six tokens each (`cell-x`, `cell-y`, `row`,
   `control`, `stack`, `section`), exposed through Tailwind's `--spacing`
   namespace via `@theme inline` (the `inline` keyword is load-bearing: it
   keeps `var(--row-h)` unresolved in the emitted utility so the attribute
   swap works at runtime). If the synced `styles.css` bakes these down to
   one set of resolved values, the sync silently broke the density feature.
2. **`stock-over` / `stock-over-surface` are intentionally defined and
   unused** (no API field backs it yet — see `DESIGN.md`). Don't build
   anything on it or treat its absence of usage as a bug.
3. `button.tsx`'s size variants (`h-8`, `h-7`, `h-9`, etc.) are static
   Tailwind heights, not `h-control`/density tokens — noted as a possible
   doc/code mismatch (`DESIGN.md` says "no component hardcodes padding, gap,
   or row height"), not something to fix here. Flag to the user if/when
   Button is synced later; out of scope for this tokens-only run.

## CSS source — points at a dev-build artifact

`cssEntry` is `.next/dev/static/chunks/src_app_globals_css_1igg3k2._.single.css`,
**not** `src/app/globals.css` directly. The raw source file uses
`@import "tailwindcss"` / `@import "tw-animate-css"` / `@import
"shadcn/tailwind.css"` — npm-package imports only Tailwind's own PostCSS
build resolves. The converter just copies whatever file `cssEntry` points
at, so it needs the *compiled* stylesheet (all imports inlined, 41 KB) —
found by grepping `.next/dev/static/chunks/*.css` for a token that's unique
to this project (`stock-ok`).

Same caveat as the fonts below: this is an uncommitted dev-build artifact.
It will disappear or rehash on a clean `.next`, and a production `next
build` may emit slightly different (likely more minified/purged) CSS.
Before any re-sync, confirm this path still exists, or better, run
`npm run build` and repoint `cssEntry` at the production equivalent under
`.next/static/`.

## Render check — skipped this run, on purpose

`package-validate.mjs --no-render-check` was used because this sync has
zero components (tokens-only) — there is nothing for the headless-Chromium
render check to actually verify. Confirmed with the user (2026-08-04); they
plan to introduce Playwright to this repo for real app testing later,
separate from design-sync's use of it. **Revisit this when components are
added** (Gate 13 / Button) — at that point the render check becomes
meaningful and Playwright + Chromium (~200MB) should be installed for it.

## Fonts — open issue, needs developer attention during build

Figtree + IBM Plex Mono are self-hosted via `next/font/google`
(`src/app/layout.tsx`), never fetched at runtime — see the comment there and
`THIRD-PARTY.md` for the attribution obligation. `next/font` writes hashed
`@font-face` CSS + woff2 files into `.next/` at build time; there is no
committed, stable font-face source in the repo.

`extraFonts` in `config.json` currently points at **dev-build** chunk paths
under `.next/dev/static/chunks/` (found via a prior `npm run dev`). These:
- are **not committed** and will disappear/rehash on a clean clone or after
  `.next` is cleared — treat this as a snapshot, not a durable path;
- come from a *dev* build; a production `next build` may hash differently
  and could be more representative of what actually ships.

**Before running the converter**, the developer should confirm these paths
still exist (`ls .next/dev/static/chunks/*font_google*`) or, better,
run `npm run build` once and repoint `extraFonts` at the equivalent files
under `.next/static/chunks/` (or wherever the prod build emits them), then
re-check this note. If `package-validate.mjs` prints `[FONT_MISSING]`
anyway, re-hunt from there — don't substitute a placeholder without asking.

## Re-sync risks

- The `extraFonts` paths are the single most likely thing to go stale (see
  above) — any `.next` clean, dependency bump, or Next version change can
  reshuffle the hashes.
- No components are synced yet, so there is nothing to verify-carry-forward
  on re-sync besides tokens/fonts. When Button (or later Gate 13 components)
  are added, this file's Scope section needs updating first.
- `styles.css`'s `@import` closure is what designs actually receive — if a
  future edit moves token declarations out of `globals.css` without updating
  `cssEntry`, the sync will silently stop picking them up.
