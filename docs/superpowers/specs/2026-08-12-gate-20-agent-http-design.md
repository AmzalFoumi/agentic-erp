# Gate 20 — the agent's own HTTP surface, loopback-only

**Date:** 2026-08-12
**Status:** approved by the developer, 2026-08-12
**Governing docs:** `docs/PLAN.md` (root), `docs/AGENT-PLAN.md` (Gates 14–21), `docs/AUTH-PLAN.md`

## Goal

Give the agent an HTTP address of its own so a browser can hold a conversation with it, with
streaming responses and with Gate 19's approval pause surviving the round trip. Deliver the
transport-only Next.js proxy that lets the frontend reach it. Do **not** build the panel — the six
UI states are Gate 21.

## The decision that shapes everything else: use the standard protocol

`pydantic_ai.ui` (2.24.0, verified in the installed package) ships two protocol adapters:
`VercelAIAdapter` (Vercel AI SDK Data Stream Protocol, consumed by `useChat` from `@ai-sdk/react`)
and an AG-UI adapter. We use **`VercelAIAdapter`**.

The alternative considered was hand-rolling our own event types over `run_stream_events`, which
would have preserved `conversation.py`'s claim that no caller needs to know Pydantic AI exists. It
was rejected on verification: hand-rolling would reinvent a documented standard, and — decisively —
`VercelAIAdapter` has **native tool-approval support**. `vercel_ai/request_types.py` defines
`ToolApprovalRequested` / `ToolApprovalResponded` parts, `_adapter.py` imports `ToolDenied`, and
`UIAdapter.deferred_tool_results` is documented as *"Deferred tool results extracted from the
request, used for tool approval workflows."*

So Gate 19's approve/deny **rides the protocol**. An approval is not a second endpoint; it is a
tool-result part inside the message list the client posts. `resume_turn`'s decision map stops being
an HTTP concern entirely.

### What this costs, stated plainly

`app.py` must import `pydantic_ai`, because `dispatch_request` takes a Starlette `Request` and an
`Agent`. So `app.py` joins Gate 17's runtime cluster, with the reason written into
`agent/pyproject.toml` beside Gate 19's `agent.tests` exemption.

Reframed honestly, the cluster is now *the files that adapt Pydantic AI to something else* —
`model_provider.py` to Google, `mcp_client.py` to MCP, `app.py` to HTTP — plus `conversation.py`,
which owns the turn. `config.py` and `scripts/` stay forbidden, and that is where the contract's
value actually was: a future caller can load settings without `pydantic_ai` on its import path.

## Wire-state ownership

`ui/_adapter.py:473-474` does:

```python
frontend_messages = self.sanitize_messages(self.messages, deferred_tool_results=...)
message_history = [*(message_history or []), *frontend_messages]
```

Server-side history and client-posted messages are **concatenated, not overridden**. Passing
`message_history` from `store.py` while `useChat` also posts its list would send the whole
conversation to Gemini twice — a silent bug that would look like the model going strange.

**Therefore: the client owns the in-flight wire state; `store.py` owns the durable record.**

- `POST /turns` passes **no** `message_history`. The client's posted list is the history.
- `on_complete` persists the finished turn through `store.append_message`.
- `GET /conversations/{id}` serves history back so a reload can hydrate `useChat`, converted with
  `VercelAIAdapter.dump_messages` — the same class that reads the wire also writes it, so there is
  one encoding, not two.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| `GET` | `/health` | `{"status": "ok", "model": ...}` |
| `POST` | `/conversations` | `{"conversation_id": 7}` |
| `GET` | `/conversations/{id}` | `{"messages": [...], "pending_since": ... \| null}` |
| `POST` | `/conversations/{id}/turns` | SSE, Vercel AI Data Stream Protocol |

One streaming endpoint, not two: it serves both "ask a question" and "resolve an approval", because
in this protocol those are the same request with a different message list.

## Persisting the pause — closing Gate 19's inherited question

Two nullable columns on `agent.conversations`, with an Alembic migration in `agent/alembic/`:

- `pending_state BYTEA` — the paused run's serialized message list, the same bytes Gate 19 returned
  as `TurnResult.resume_state`.
- `pending_since TIMESTAMPTZ` — when the pause began.

Written when a turn pauses, cleared when it completes. `on_complete` is the single hook for both: a
deferred pause **is** a successfully completed run whose `output` is a `DeferredToolRequests`, so
the callback branches on that type — pause → write the columns; otherwise → append the messages and
clear the columns.

Keeping the pause in its own columns rather than as `messages` rows preserves Gate 19's invariant
that *a half-finished turn is not conversation history*.

`GET /conversations/{id}` returns `dump_messages(pending_state)` when it is set, so a reload
re-renders the approval card from the same bytes, and `pending_since` so the UI can show staleness.

**One source of truth.** The stored bytes are for *reload*; the resume itself is carried by the
protocol, from the client's posted message list. These do not compete: the client cannot resume a
conversation it has forgotten, and the stored bytes are how it remembers.

### Gate 19's three deferred questions, answered

| Question | Answer |
|---|---|
| Who expires abandoned approvals? | `pending_since` is stored so staleness is **visible**. **No automatic sweeper this gate** — expiry needs a policy nobody has set. Deliberate, not forgotten. |
| Is a stale approval still valid? | No, and it cannot be made valid. This is the already-documented "approval is not authorization" gap: the window between approving and executing is never zero. Unchanged by this gate. |
| How sensitive is a stored "when approved, write this"? | Same sensitivity as `agent.messages`, and it gets the same protection — RLS deny-all on the `agent` schema. Real protection waits on auth. |

## The `Actor` seam

`agent/actor.py` — a deliberate **copy** of `backend/core/actor.py`'s `Actor` Protocol and
`SystemActor`, not an import, for the same reason `agent/config.py` is a copy: `agent/` reaches the
ERP only over MCP, and importing `backend.core` would cross the boundary the design exists to hold.

`actor` becomes a keyword-only parameter on `run_turn`, `resume_turn`, and the new public
`build_agent`, and is passed to `ErpToolset`, which stores it and does nothing with it yet. That is
the point: `ErpToolset.call_tool` is where per-call MCP `_meta` identity attaches when auth lands,
and the parameter existing now means that is a one-file change rather than a retrofit through an
HTTP-shaped approval path — the "known trap" `CLAUDE.md` names for `mcp_server/server.py`'s
`_actor()`.

**Provider agnostic by construction.** Nothing in `agent/` imports an auth library or names a
provider type. The seam carries a Protocol with `id` and `can()` and nothing else, so adopting
ThunderID, Asgardeo, or anything else remains a change to `get_actor()` — see `docs/AUTH-PLAN.md`,
which owns that comparison and must not be re-researched here.

## The loopback bind, written down

Explicit and commented in `app.py`, not inherited from a uvicorn default, per the developer's
decision:

```python
# 127.0.0.1, not 0.0.0.0, and not a default we inherited. There is no auth on
# this surface: /turns will run a write tool against the ERP if a human at
# *some* browser approves it, and nothing here knows which human. ...
HOST = "127.0.0.1"
PORT = 8002
```

Port 8002 — 8000 is FastAPI, 8001 is the MCP server.

**Deployment waits for the auth gate**, decided by the developer this session. A deployed frontend
has no route to a loopback port, so the proxy route is local-only *by construction*. That is a
design fact, not a limitation to work around: per `docs/PLAN.md`, putting a tunnel, reverse proxy,
Docker port publish, or cloud deployment in front of this surface expires the auth deferral and the
login gate lands first.

## The Next.js proxy route

`frontend/src/app/api/agent/[...path]/route.ts` — transport only. Forwards method, body, and the
`Accept` header to `${process.env.AGENT_BASE_URL}/${path}`, and returns the upstream `Response`
**as-is** so the SSE body streams through unbuffered rather than being read into a string. No
parsing, no interpretation of the protocol, no business logic. It exists because the browser cannot
reach a port only the server can address, and it keeps `AGENT_BASE_URL` server-side.

`AGENT_BASE_URL` in `frontend/.env.example` — reserved and empty since Gate 9 — gets its value,
`http://127.0.0.1:8002`.

### Two ESLint carve-outs

`docs/AGENT-PLAN.md` line 490 anticipates one amendment; two are needed, both scoped to that exact
file path, both with the reason in a comment:

1. **Rule 1** (`no-restricted-globals` on `fetch`) currently ignores only `src/lib/api/**`. The
   proxy must call `fetch`.
2. **Rule 2** bans the *existence* of any file under `src/app/api` via a `Program` selector. The
   proxy must exist.

Rule 2 deserves a straight answer, because stopping a third adapter is its whole purpose. **This is
not a third adapter**, and the distinguishing test is: *does it mirror an endpoint that already
exists elsewhere?* `src/app/api/products` would mirror FastAPI — banned, and stays banned. This
route mirrors nothing; it *reaches* a service the browser cannot address, exactly the "webhook
receiver, OAuth callback" case Rule 2's own comment anticipated. The rule keeps its teeth: one
glob, still `error`, zero handlers permitted anywhere else.

## Tests

Following Gate 19's precedent — tests, not a live demo, because a denial cannot be demonstrated
against a live model. `agent/tests/test_app.py`, using FastAPI's `TestClient` with Gate 19's
`scripted_model` and `RecordingToolset` injected, and `store.py` calls faked so no test touches
Postgres:

1. `GET /health` returns 200 and names the configured model.
2. A read question streams: the response body is SSE and carries the answer text.
3. A mutating question streams a tool-approval part **and `RecordingToolset.executed == []`** — the
   HTTP path does not weaken the gate.
4. Posting the approval response resumes and the toolset records the tool ran with the original
   arguments.
5. Denying resumes and the toolset records that it did not run.
6. `HOST == "127.0.0.1"` — cheap, and it turns the auth-deferral constraint into something that
   fails loudly if edited.

`lint-imports` must pass with `agent.app` admitted to the cluster and `agent.config` /
`agent.scripts` still forbidden.

## Dependencies

Added to `agent/requirements.txt`, matching `backend/requirements.txt` exactly per that file's
established convention ("one library, two services, no reason to drift"):

- `fastapi==0.141.0` (0.141.1 is current on PyPI; matching the backend wins)
- `uvicorn[standard]==0.52.0`
- `httpx==0.28.1` — needed by `TestClient`; present transitively via `mcp` today, which is a latent
  break, so it becomes intentional.

## Not in this gate

The `useChat` wiring and the six panel states (Gate 21); any approval-expiry sweeper; any
deployment; any change to the auth deferral.

## Doc corrections owed at gate close

- `docs/PLAN.md` progress-table row 20.
- `docs/AGENT-PLAN.md`: the Gate 20 section, the "resume_state is not persisted" note at ~1156
  (now resolved), and line 490's single-amendment claim about ESLint (two are needed).
