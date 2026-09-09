# Chatbot overhaul — design spec

> **Status:** IMPLEMENTATION IN PROGRESS. Gate 31 (chat mode), 32 (Markdown rendering), and 33
> (structured tool-output contract) complete on branch `feat/client/chatbot`, pending review
> (commits `e306d05..72f8ded` for gate 33). Gate 34 (response cards) depends on 33 and is next.
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

> **Design finalised 2026-09-10** (brainstorm this session). Three decisions locked (Q1–Q3
> below). Supersedes the "Fix" sketch that was here before. Implementation plan:
> `docs/superpowers/plans/2026-09-10-gate33-structured-tool-output.md`.

**Problem, restated after reading the installed `mcp` 2.0.0 SDK source.** The spec's finding 2
("`output` is a string of newline-concatenated JSON objects") is a real symptom but the cause is
**not** the backend. `@mcp.tool()` already builds a structured-output object for every read tool,
from the return-type hint — the SDK's `func_metadata.convert_result` populates
`CallToolResult.structured_content` today, and `backend/tests/test_mcp_products.py` already reads
`.structured_content` as a dict. The concatenated-JSON string is produced **entirely** by
`agent/mcp_client.py:call_tool`, which does `"\n".join(block.text …)` over the *unstructured*
`result.content` blocks and discards `structured_content`.

So gate 33 is two coordinated changes, not the big backend lift the earlier sketch implied:

1. **Agent:** `call_tool` prefers `structured_content`. This alone fixes the wire format.
2. **Backend:** replace the loose `-> dict[str, Any]` / `-> list[dict[str, Any]]` return hints
   with **named Pydantic models**. The loose hints *do* produce `structured_content`, but the
   JSON Schema attached to it is useless for a type contract (`{"type": "object"}` with no named
   properties; and a bare `list[...]` return is auto-wrapped by the SDK as `{"result": […]}`).
   Named models give a real schema to generate TypeScript from, and a real contract to drift-check.

**Q1 — list-tool output shape (decided: named field + count where cheap).**
- `list_products` → `{ "products": [ProductOut, …], "total": int }` — `total` from the **existing**
  `services/products.py:count_products` (no new query, no service change).
- `list_product_lots` → `{ "lots": [LotOut, …] }`
- `list_pending_drafts` → `{ "drafts": [DraftOut, …] }`
- `list_purchase_orders` → `{ "orders": [PurchaseOrderOut, …], "total": int }` — shape unchanged.
- Rejected: adding `total` to lots/drafts (needs count queries in `services/` — over the line);
  a generic `{ "items": [...] }` envelope (loses the self-describing field name in the raw JSON
  the model reads).

**Q2 — TypeScript generation (decided: offline, via a committed schema file).**
- New `backend/mcp_server/dump_schemas.py`, run as `python -m mcp_server.dump_schemas`. Pure model
  introspection — no server, no DB. Writes a deterministic JSON Schema document to
  `frontend/src/lib/api/mcp-schema.json` (backend writes into the frontend tree, exactly as the
  REST `schema.d.ts` already lives there).
- Frontend `npm run mcp:types` turns `mcp-schema.json` → `src/lib/api/mcp-types.d.ts` with a
  standard JSON-Schema→TypeScript generator (one new **dev** dependency; exact package chosen at
  implementation per verify-docs).
- **Drift check is two halves**, because regenerating the schema needs Python: CI's backend job
  runs `dump_schemas` and `git diff --exit-code` on `mcp-schema.json`; CI's frontend job runs
  `mcp:types` and diffs `mcp-types.d.ts`. `npm run mcp:types:check` is the frontend half.
- Both generated files: **committed, never hand-edited** — same rule as `schema.d.ts`.
- Rejected: generating from a live MCP server (mirrors `api:types` but the MCP server now needs
  auth, so it needs a dedicated `AUTH_ENABLED=false` run in CI); backend emitting the `.d.ts`
  directly (backend then owns frontend codegen + a generator in the backend venv).

**Q3 — scope: write/proposal tools too (decided: yes, type the shared helpers).**
The `_describe` / `_describe_lot` / `_describe_draft` helpers are shared by read tools **and** by
`create_product`, `update_product`, `adjust_stock`, `receive_stock_lot`, `create_action_draft`,
`propose_spoilage_markdown`, `propose_reorder_order`, `propose_delivery_receipt`. Typing the
helpers is the least-code path and it hands those helpers a single source of truth for the field
list. All ~15 tool outputs get named models + generated TS. This slightly exceeds the earlier
"read tools" wording but is still pure serialization — no `services/`, `core/`, `authn/`, or
auth-path file is touched, and MCP tool **descriptions** (docstrings) are unchanged.

**Components.**
- `backend/mcp_server/schemas.py` (new) — `ProductOut`, `LotOut`, `DraftOut` and the nested row
  models (`SpoilageItemOut`, `ReorderBundleOut`/`ReorderLineOut`, `PurchaseOrderOut`/`POLineOut`,
  `UnsourcedOut`), plus the result wrappers (`ProductListOut`, `LotListOut`, `DraftListOut`,
  `SpoilageReportOut`, `ReorderReportOut`, `PurchaseOrderListOut`). Money fields typed `str`.
  Nullable stays nullable. `DraftOut.payload` stays `dict[str, Any]` — polymorphic by
  `draft_type` (finding 10); the gate-34 card switches on `draft_type` at runtime. Deliberate
  hole, documented in the model.
- `backend/mcp_server/server.py` — `_describe*` helpers return their models; each tool's return
  annotation becomes its model; list tools build the wrapper. `translated` decorator unchanged
  (it passes return values straight through — verified 2026-09-10).
- `backend/mcp_server/dump_schemas.py` (new) — see Q2.
- `agent/mcp_client.py:call_tool` — success path returns `result.structured_content` when
  present, else the current text join (covers any future tool with no model). Error path
  unchanged. Stays inside the gate-17 isolation cluster; no auth, no `conversation.py`, no
  `app.py`. The module docstring line listing "structured content" among things "we do not do"
  is updated.
- `frontend/package.json` — `mcp:types`, `mcp:types:check` scripts + the generator dev dep.
- `frontend/src/lib/api/mcp-schema.json`, `frontend/src/lib/api/mcp-types.d.ts` — generated,
  committed.

**Test (backend pytest — TDD applies here; frontend has no test runner — `tsc`/`lint` only).**
Per tool: `structured_content` validates against its model; `list_products.total` is correct;
wrapper keys present. A test that regenerates the schema in-process and compares to the committed
`mcp-schema.json` (so CI catches drift even without the npm step). Existing MCP tests still pass.
Agent: `call_tool` returns an object when `structured_content` exists and the text fallback still
works when it does not.

**What gate 33 owes the demo box: nothing.** No new permission, no new setting, no migration.
State this explicitly in `docs/DEPLOY-PLAN.md`'s "what a new feature has to update in the box".

**Deferred / verify-at-implementation (durable — do not drop across a compaction):**
- `DraftOut.payload` left as a loose object; a discriminated union keyed on `draft_type` is a
  later refinement, not gate 33.
- ~~Verify how Pydantic-AI's `VercelAIAdapter` serializes a **dict** tool-return into the streamed
  `tool-output-available.output` field.~~ **RESOLVED 2026-09-10.** `pydantic_ai.ui.vercel_ai._utils.tool_return_output`
  is `tool_return_ta.dump_python(part.content, mode="json")` — a plain dict passes through unchanged
  (verified empirically in the agent venv, both directions). So `output` is now a JSON object where
  pre-gate-33 it was the `}\n{`-concatenated string. Same function serves the live stream and the
  `dump_messages` history path.
- ~~Verify the chosen JSON-Schema→TS generator resolves `$ref`/`$defs` and keeps string-typed money
  as `string`.~~ **RESOLVED 2026-09-10.** `json-schema-to-typescript@16` via a wrapper script
  (`frontend/scripts/gen-mcp-types.mjs`); money fields are `string` in `mcp-types.d.ts`, `$defs`
  resolve to named interfaces.
- Bare-list / non-str-key returns still trigger the SDK's `{"result": …}` auto-wrap. We avoid it
  by using models everywhere; `call_tool` keeps only the text fallback, not a de-wrap. If a
  future tool returns a bare collection, revisit.
- Gate 34 consumes `mcp-types.d.ts` for the card registry and the reload-persistence work — it is
  a hard dependency, tracked in the phasing table.

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

- Streamdown vs `react-markdown` current versions + Tailwind v4 compat (gate 32). **Resolved —
  gate 32 shipped on Streamdown 2.6.0.**
- Gate 33 **shipped 2026-09-10** (commits `e306d05..09b5714` on `feat/client/chatbot`). All its
  verify-at-implementation items in the Gate 33 section above are now resolved, including the
  `VercelAIAdapter` dict-serialization question (`tool_return_output` passes a dict through as a
  JSON object). End-to-end browser check deferred — the frontend dev server was not hydrating at
  the time; the wire behaviour was confirmed at the serializer instead.
- Whether `VercelAIAdapter.dump_messages` on the GET path already round-trips tool parts when
  they are present in `provider_data` (gate 34).
- Tool dict shapes are captured (table above); re-capture at gate 33 start only if `server.py`
  changed since 2026-09-09.
