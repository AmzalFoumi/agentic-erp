# Chatbot overhaul — design spec

> **Status:** IMPLEMENTATION IN PROGRESS (2026-09-09). Chat mode (gate 31) and Markdown rendering
> (gate 32) are complete and pending review; gates 33–34 have not started, per `docs/PLAN.md`.
> **Owner doc.** This is the single source of truth for the chatbot overhaul. `docs/PLAN.md`
> gates 31–34 point here and carry only one-line summaries. Do not restate decisions in other
> docs — link to this file.
>
> **Subordinate to `docs/PLAN.md`.** Where they disagree, PLAN.md wins.

## Why

The agent panel (`frontend/src/components/shell/agent-panel/`, built at gate 21) works but has
three rough edges:

1. **It is a fixed 256px right rail only.** No way to give the conversation room.
2. **Responses are raw text blobs.** `MessageList` renders only `text` parts, as plain strings —
   Markdown shows literally (`**bold**`, `* bullet`), and when a tool returns a list the model
   re-types every row into prose. The structured data the tools already produce is discarded.
3. **No Markdown rendering at all**, so even a well-formatted answer reads as a wall of text.

## Hard constraints (do not violate)

- **No routing changes.** No new routes, no route renames, no changes to `src/proxy.ts` or
  `src/app/api/agent/[...path]/route.ts` behaviour.
- **No auth / permission / ThunderID changes.** No new scopes, no Console changes, no token
  handling changes. The `deploy/aisle-box/` config is not touched by this work.
- **Backend changes are allowed** only where they are pure data-shape / serialization (gate 33's
  `outputSchema`), never touching `services/`, `authn/`, `api/deps.py`, `api/errors.py`, or the
  MCP auth path.
- **The one architecture rule holds.** `services/` unchanged. `agent/` isolation cluster
  (`conversation.py`, `model_provider.py`, `mcp_client.py`, `app.py`) is the only place framework
  types live; `store.py` / `app.py` persistence still sees only our own shapes.
- **Loopback binding stays.** `agent/app.py`'s `HOST = "127.0.0.1"` is not touched.

---

## Verified against the running system — 2026-09-09

Captured live: dev stack up via `scripts/dev-up-timed.sh` (api :8000, mcp :8001, agent :8002,
frontend :3000), ThunderID container `thunderid-local` up on :8090, signed in as test user
`amzal`. Raw SSE captured from `POST /api/agent/conversations/{id}/turns` for **all 7 read
tools** in the card registry (`list_products`, `get_product_by_sku`, `check_spoilage_risk`,
`suggest_reorder_bundles`, `list_pending_drafts`, `list_purchase_orders`, `list_product_lots`) —
raw dumps in the session scratchpad.

### The wire contract (this is what the cards consume)

The agent streams the **Vercel AI Data Stream protocol** (`x-vercel-ai-ui-message-stream: v1`),
produced by `pydantic_ai.ui.vercel_ai.VercelAIAdapter`. For a turn that calls a read tool:

```
data: {"type":"start"}
data: {"type":"start-step"}
data: {"type":"tool-input-start","toolCallId":"call_2627073","toolName":"get_product_by_sku", ...}
data: {"type":"tool-input-delta","toolCallId":"call_2627073","inputTextDelta":"{\"sku\":\"2002-1001\"}"}
data: {"type":"tool-input-available","toolCallId":"call_2627073","toolName":"get_product_by_sku","input":{"sku":"2002-1001"}, ...}
data: {"type":"tool-output-available","toolCallId":"call_2627073","output":"{\n  \"id\": 143, ... }"}
data: {"type":"finish-step"}
data: {"type":"start-step"}
data: {"type":"text-start","id":"..."}
data: {"type":"text-delta","delta":"Here are the details for **Full Cream Milk 1L** ...","id":"..."}
data: {"type":"text-end","id":"...", "providerMetadata":{"pydantic_ai":{...thought_signature...}}}
data: {"type":"finish-step"}
data: {"type":"finish","finishReason":"stop"}
data: [DONE]
```

On the **client** (`useChat`), the assistant message ends up with `parts`:
`[{type:"step-start"}, {type:"tool-<toolName>", toolCallId, state:"output-available", input, output, callProviderMetadata}, {type:"step-start"}, {type:"text", text, providerMetadata}]`.
This matches `use-panel-state.ts`'s existing `ToolUIPart` shape.

### Findings that shape the design

1. **Read-tool outputs DO reach the browser** — as `tool-output-available` with `output`. So
   Option 1 (render existing outputs) is viable with no new agent tools. ✅ the core assumption.

2. **`output` is a STRING, not structured JSON — and two different string shapes.** All 7 read
   tools were captured live 2026-09-09 (see the shapes table below). Two families:
   - **Concatenated bare objects** (`list_products`, `list_product_lots`, `list_pending_drafts`):
     N pretty-printed JSON objects glued with `\n` between them — **NOT a JSON array.** Parsing
     means splitting on `}\n{` or a streaming JSON-objects parser. Fragile.
   - **One clean object** (`get_product` / `get_product_by_sku` — single; `check_spoilage_risk`,
     `suggest_reorder_bundles`, `list_purchase_orders` — an object that *wraps* its own array,
     e.g. `{"orders":[...],"total":2}`, `{"total_value":"…","bundles":[…],"unsourced":[…]}`,
     `{"scanned_on":"…","items":[…]}`). These parse with a plain `JSON.parse` today.

   So gate 33's `outputSchema` work is strictly needed for the 3 concatenated-object tools and is
   cheap insurance (a typed contract + drift check) for the other 4. **This is the concrete
   justification for gate 33** (`outputSchema` / `structuredContent` → `output` becomes a real
   array/object for all of them).

3. **The model re-lists everything in prose**, already as Markdown:
   `"* **Sparkling Water 1.5L** (Beverages) — 0 bottles on hand (reorder level: 24)\n* ..."`.
   So (a) the Markdown renderer (gate 32) is an immediate win on its own, and (b) gate 34 needs
   an `INSTRUCTIONS` line telling the model not to re-type tool list data.

4. **Money is precision-safe in the tool output** (`"cost_price": "380.00"` as a string) but the
   model's prose drops it to `380.00` with no `Rs` and no grouping. Cards render money correctly
   via `frontend/src/lib/format.ts` where the prose does not.

5. **`updated_by` is a raw value** — a UUID (`01a02d8f-...`), or the literal `"api"` / `"mcp"`.
   Not display-ready. Cards should hide it or resolve it, not print the UUID.

6. **`thought_signature` provider metadata rides on `tool-input-*` and `text-end` parts.** Must
   be preserved through any history round-trip (it already is — `agent/app.py` handles this).
   Relevant to gate 34's reload-persistence change: whatever extra parts get persisted must keep
   `providerMetadata` intact.

7. **ThunderID permissions for `amzal` are already fully provisioned** — the session token
   carries `product.read product.create product.update stock.adjust draft.read draft.create
   draft.decide lot.read lot.write purchasing.read purchasing.write`. (Several PLAN.md notes
   still say `lot.*` / `purchasing.*` are "pending on the login server" — stale for this user's
   token, but **out of scope: do not touch ThunderID.**)

8. **One assistant turn can carry several tool parts.** "List the lots for SKU 2002-1001" ran
   `get_product_by_sku` **then** `list_product_lots` in one message → `parts` had two
   `tool-*` parts (plus two `step-start`) before the text. The card renderer must iterate every
   `tool-*` part in the message, not assume one — render a card per part, in order.

9. **Nested rows carry only `product_id`, never a name.** `list_pending_drafts.payload.lines[]`,
   `list_purchase_orders.orders[].lines[]`, `suggest_reorder_bundles.bundles[].lines[]` — all
   identify products by numeric id only (bundles also include `name`/`sku`, drafts and POs do
   not). Cards that show line items must resolve names client-side (the existing
   `getProductSummary` / `useProductLabel` path in `tool-call-card.tsx`) or show the id.

10. **`list_pending_drafts.payload` is polymorphic by `draft_type`.** `SUPPLIER_REORDER` →
    `{supplier_id, expected_date, lines:[{product_id, quantity, unit_cost}]}`;
    `BATCH_PRICE_MARKDOWN` → `{lines:[{lot_id, product_id, new_price}]}`. Card must switch on
    `draft_type`. Also every draft carries `is_expired`, `reasoning`, `cost_at_risk` (nullable),
    `projected_recovery` (nullable), `created_via`.

### Tool return shapes — captured live 2026-09-09 (raw SSE in scratchpad; for the card registry)

`str(...)` = wire delivers it as a JSON *string* today; **‖** = concatenated bare objects, not an
array (finding 2). All money fields are strings (`"380.00"`).

| Tool | `output` shape (exact) | Card |
|---|---|---|
| `list_products` | ‖ objects: `id, sku, name, category, unit, cost_price, sell_price, quantity_on_hand, reorder_level, needs_reorder, updated_by` | `ProductListCard` |
| `get_product`, `get_product_by_sku` | one object, same fields as above | `ProductCard` |
| `check_spoilage_risk` | one object: `scanned_on, within_days, total_cost_at_risk, total_projected_recovery, items:[{lot_id, product_id, sku, product_name, lot_code, expiry_date, days_remaining, quantity, current_price, proposed_price, discount_percent, why, cost_at_risk, projected_recovery}]` | `SpoilageCard` |
| `list_product_lots` | ‖ objects: `lot_id, product_id, lot_code, expiry_date(nullable), quantity, cost_price, sell_price, discount_percent, is_expired` | `LotsCard` |
| `suggest_reorder_bundles` | one object: `total_value, bundles:[{supplier_id, supplier_name, lead_time_days, minimum_order_value, bundle_value, below_minimum, shortfall, lines:[{product_id, sku, name, quantity_on_hand, reorder_level, quantity, unit_cost, pack_size, line_total, is_top_up}]}], unsourced:[{product_id, sku, name, quantity_on_hand, reorder_level}]` | `ReorderBundlesCard` |
| `list_pending_drafts` | ‖ objects: `id, draft_type, status, payload(polymorphic, finding 10), reasoning, cost_at_risk(nullable), projected_recovery(nullable), expires_at, is_expired, created_by, created_via, decided_by, decided_via` | `PendingDraftsCard` |
| `list_purchase_orders` | one object: `total, orders:[{id, supplier_id, status, expected_date(nullable), total_value, notes(nullable), source_draft_id, created_by, lines:[{product_id, quantity_ordered, unit_cost, line_total}]}]` | `PurchaseOrdersCard` |
| `propose_spoilage_markdown`, `receive_stock_lot`, `propose_reorder_order`, `create_action_draft`, `propose_delivery_receipt` | mutation / draft result | existing approval + success cards |
| `adjust_stock`, `create_product`, `update_product` | one product object | existing `SuccessCard` |

Not display-ready in any of these: `*_by` fields (raw UUID or `"api"`/`"mcp"`), `supplier_id`
without a name (only bundles include `supplier_name`), nested `lines[]` `product_id` without a
name (finding 9).

---

## Priority 1 — fullscreen / expand mode  → Gate 31

**Decision (user, 2026-09-09): "replace content area".** When expanded, the chat fills the
`<main>` region; the page is hidden but stays mounted. Top navbar + side nav always visible.

### Mechanics

- New client component `frontend/src/components/shell/chat-shell.tsx` wraps the `<main>` +
  `<AgentPanel>` region in `layout.tsx`. `layout.tsx` stays a Server Component; `children` (the
  page) is still server-rendered and passed in as a prop.
- `chat-shell.tsx` owns `mode: "docked" | "expanded"`.
  - `docked` (today): `<Nav />` · `<main class="flex-1">{children}</main>` · `<AgentPanel class="w-64">`
  - `expanded`: `<Nav />` · `<div hidden>{children}</div>` · `<AgentPanel class="flex-1">`
- The page wrapper uses the `hidden` attribute (`display:none`) — **mounted, not unmounted.**
  Scroll position and page client state survive. No navigation, no refetch, nothing for
  ThunderID to re-evaluate. `/api/agent/*`, `<SignedIn>`/`<SignedOut>`, and all routes untouched.
- **Persistence:** `localStorage` key `agent-panel-mode`, same pattern as the density toggle and
  the stored conversation id. Read inside the panel's existing pre-mount effect (already renders
  a "Connecting…" placeholder before `conversationId` resolves), so no flash.
- **Controls:** expand/collapse icon-button in the panel header next to the existing `X`; `Esc`
  collapses.
- **Readability when expanded:** message column gets `max-w-3xl` centered. Cards that need width
  (tables) may break to a wider inner max-width.

### Out of scope

Auto-expand on small screens (follow-up). Any change to what the page routes to.

### Test

Toggle expand → page hidden, nav + header still there, conversation state intact. Toggle back →
page reappears at same scroll position, no network request fired for the page. Reload while
expanded → returns in `expanded` (localStorage). Component test on `chat-shell.tsx` mode switch.

---

## Priority 3 — Markdown rendering  → Gate 32

*(Built before gate 34 because gate 34's fallback card and in-card prose both need it.)*

**Text parts render as Markdown** instead of `{text}`. New component
`frontend/src/components/shell/agent-panel/markdown.tsx`, used by `MessageList` and by any card
that shows model prose.

### Library

One new frontend dependency (developer runs `npm install`). Candidates, decide at implementation
after verifying current versions and Tailwind v4 compatibility:

- **Streamdown** (Vercel) — built on `react-markdown` + `remark-gfm`, hardened for streaming
  (unterminated code fences, half-written tables), sanitizes, `allowedLinkPrefixes` /
  `allowedImagePrefixes`. AI-SDK-native. **Leaning this way.**
- **`react-markdown` + `remark-gfm` + `rehype-sanitize`** — smaller, more control, every element
  mapped to design tokens by hand. Fallback if Streamdown's bundled styling fights the token
  system.

Either way: override styling to design tokens (Figtree / IBM Plex Mono, `--radius`), code blocks
in mono, links open in new tab with `rel="noreferrer"`, constrain to safe schemes.

### Scope

Frontend only. `components/shell/agent-panel/`. No backend, no `agent/` changes.

### Test

`**bold**`, bullet lists, tables, inline code, code fences all render. A half-streamed fence does
not crash. Links are sanitized. Renders correctly in dark mode and both densities.

---

## Priority 2 — structured response cards  → Gates 33 + 34

**Decision (user, 2026-09-09): Option 1 (render existing tool outputs) + escape hatch.** No
dedicated "render" agent tools. See the rejected alternative and its ramifications at the end.

### Gate 33 — structured tool-output contract (backend + generated types)

**Problem:** `output` is a string of newline-concatenated JSON (finding 2). Parsing it
client-side is fragile, and there is no type check the way `schema.d.ts` gives the REST client.

**Fix:**
- Give the MCP **read** tools (`list_products`, `get_product`, `get_product_by_sku`,
  `check_spoilage_risk`, `list_product_lots`, `suggest_reorder_bundles`, `list_pending_drafts`,
  `list_purchase_orders`) Pydantic return models / MCP `outputSchema` so the SDK emits
  `structuredContent` — `output` becomes a real array/object.
- This is a serialization/declaration change in `backend/mcp_server/`. **`services/` untouched;
  `_describe()` already picks the fields; no auth path touched.** Verify against the installed
  `mcp` SDK's `outputSchema` / `structuredContent` API at implementation (verify-docs rule — the
  SDK is new).
- **Generate TypeScript types** from those schemas into `frontend/src/lib/api/` (a sibling of
  `schema.d.ts`), plus a **drift check** mirroring the existing `api:types` check. This is the
  card registry's contract — the thing that makes a backend field rename a failed check, not a
  silently broken card.
- Keep MCP tool **descriptions** (the docstrings the model reads) unchanged — only the return
  declaration changes.

**Shapes are already captured** (see the "Tool return shapes" table above — all 7 read tools
captured live 2026-09-09). At gate start, re-capture only if `server.py` / `_describe()` has
changed since, and diff against the table.

**Test:** each read tool's `structuredContent` matches its declared schema; existing MCP tests
still pass; the drift check fails on a deliberate schema change.

### Gate 34 — the cards, reload persistence, prompt tuning

**Card registry.** `frontend/src/components/shell/agent-panel/cards/` — a map
`tool-<name>` → component. In the message list, iterate **every** `tool-*` part in the assistant
message (a turn can have several — finding 8); each part with `state:"output-available"` and no
pending approval renders `registry[part.type]?.(parsed output) ?? <FallbackCard>`, in order.
No tool name is hardcoded outside the registry (matches the existing Global Constraint in
`use-panel-state.ts`). Cards with line items resolve `product_id` → name via the existing
`getProductSummary` path (finding 9), not by assuming a name in the payload.

**Cards** (hand-built from shadcn/base-nova primitives + tokens; reuse `StockBadge`,
`format.ts`, `Skeleton`; inspiration only from Vercel `ai-elements`, `assistant-ui`, shadcn chat
blocks):

| Card | Content | Row cap / link |
|---|---|---|
| `ProductListCard` | table: SKU · name · stock · `StockBadge` · sell price | ~5 rows, then "view all N in Products →" (`/products?search=`) |
| `ProductCard` | all fields, `needs_reorder` badge, money via `format.ts` | links: product detail / edit / adjust-stock / lots |
| `SpoilageCard` | at-risk lots, expiry, recoverable value, markdown ladder | `/inventory/spoilage` |
| `LotsCard` | batches soonest-expiry-first: qty · expiry · cost | product page |
| `ReorderBundlesCard` | grouped by supplier: lines, MOQ top-up, order total | `/purchasing` |
| `PendingDraftsCard` | draft type · summary · age | `/approvals` |
| `PurchaseOrdersCard` | PO · supplier · status · total | `/purchasing/orders/[id]` |
| `FallbackCard` | collapsible key/value / JSON for any unregistered tool | — |

**Shared:** `ChatCard` shell (border, `bg-card`, padding, title slot) + `ChatCardTable` (dense,
`tabular-nums`, row cap + overflow link). Restyle existing `ToolCallCard` (approval) and
`SuccessCard` (mutation) to the `ChatCard` shell — they stay the write-side.

**Reload persistence.** Today `conversation.py:_completed` persists only
`result.new_messages()[-1]` (the final text), so tool parts — and therefore cards — vanish on
refresh. Persist enough of the run for cards to re-render:
- Extend what `_completed` serializes into `Message.provider_data` (or an additional field) to
  include the tool-call / tool-return messages, keeping `providerMetadata` / `thought_signature`
  intact (finding 6).
- `Message` type and `to_model_history` / `VercelAIAdapter.dump_messages` on the GET path must
  round-trip the tool parts. Stay inside the isolation cluster; `store.py` still persists opaque
  bytes.
- Decide at gate start: persist the whole `result.all_messages()` for the turn vs. just the
  tool-call/return + final text. Whole-turn is simpler and matches what `_paused` already does
  for the pending case.

**Prompt tuning.** One line in `agent/conversation.py`'s `INSTRUCTIONS`: when a tool returns a
list, give a one-sentence summary and do not re-type its rows — the interface shows the detail.
Accept that Flash-Lite / Gemma will not obey 100%; the card is correct regardless.

**Test:** each card renders from a fixture matching gate 33's schema; unregistered tool →
fallback; card survives a page reload (new persistence); approval + success cards still work;
`npm run lint` (restricted-import rules) and `npx tsc --noEmit` clean; agent tests pass.

---

## Phasing summary

| Gate | Scope | Depends on | Independent? |
|---|---|---|---|
| 31 | Fullscreen/expand mode | — | yes, ship first |
| 32 | Markdown rendering | — | yes |
| 33 | MCP `outputSchema` + generated TS types + drift check | — | backend, yes |
| 34 | Card registry + cards + reload persistence + prompt line | 32, 33 | no |

Each gate ends with the standard stop-and-commit discipline (`docs/PLAN.md`).

---

## Rejected alternative — dedicated "render" agent tools (the luxskin approach)

New MCP tools whose only job is to emit UI-component payloads for the agent to call.
Rejected because:

- **Reliability:** the model must read tool JSON back and re-emit it as an argument without
  dropping rows, mangling `"19.99"` into a float, or hallucinating. Flash-Lite / Gemma are weak
  at this (AGENT-PLAN records Gemma reaching for tools reluctantly). Reintroduces the precision
  bug the whole codebase avoids.
- **Cost:** ~2× model round trips per rich response; free-tier RPD is ~500.
- **Surface:** every render tool is a new tool the model can misuse and that needs testing.
- **Architecture:** a tool that exists to make the browser draw a table is presentation logic in
  `mcp_server/` — bends the "translate data for a model to read" thesis.
- luxskin needed it because its data tools returned prose / raw upstream shapes. Aisle's
  `_describe()` is already a deliberate typed contract — a better starting point.

Kept in reserve for one case only: a card the model genuinely *composes* (a narrative plan) —
and even then, structured tool output is preferred.

---

## Open items to verify at implementation (verify-docs rule)

- Streamdown vs `react-markdown` current versions + Tailwind v4 compat (gate 32).
- Installed `mcp` SDK `outputSchema` / `structuredContent` API and how Pydantic AI's
  `VercelAIAdapter` surfaces structured content in `tool-output-available` (gate 33). Open
  question: does `structuredContent` change the `tool-output-available.output` field in place, or
  add a sibling field the client must read instead?
- Whether `VercelAIAdapter.dump_messages` on the GET path already round-trips tool parts when
  they are present in `provider_data` (gate 34).
- Tool dict shapes are captured (table above); re-capture at gate 33 start only if `server.py`
  changed since 2026-09-09.
