/**
 * The one route handler in this tree. Transport only.
 *
 * **Why it is allowed to exist, when `eslint.config.mjs` Rule 2 bans the
 * existence of any file under `src/app/api`.** That rule stops a *third
 * adapter* — a handler mirroring an endpoint FastAPI already serves, so the same
 * operation exists in three places and drifts in two. The test is: does it
 * mirror something? `src/app/api/products` would; it stays banned. This mirrors
 * nothing. It *reaches* a service the browser cannot address, which is exactly
 * the "webhook receiver, OAuth callback" case Rule 2's own comment anticipated.
 *
 * The agent service binds to 127.0.0.1 (see `agent/app.py`'s HOST comment — that
 * is load-bearing for the auth deferral, not a config choice). The Next server
 * can reach it; a browser tab cannot. So this forwards, and `AGENT_BASE_URL`
 * stays server-side.
 *
 * **A deployed frontend cannot use this route**, by construction: there is no
 * route from a deployed host to a developer's loopback port. That is the
 * intended shape, not a gap to work around. Per `docs/PLAN.md`, putting a
 * tunnel, reverse proxy, or cloud deployment in front of the agent expires the
 * auth deferral and the login gate lands first.
 *
 * Nothing here parses the protocol. The upstream `Response` is returned as-is so
 * the SSE body streams through unbuffered — reading it into a string first would
 * turn a live stream into a single delivery at the end, which is the whole thing
 * the streaming protocol exists to avoid.
 */

const AGENT_BASE_URL = process.env.AGENT_BASE_URL;

async function proxy(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  if (!AGENT_BASE_URL) {
    // A missing base URL is a setup mistake, not a runtime condition. Named
    // here rather than surfacing as a fetch failure against "undefined/health".
    return Response.json(
      { error: "not_configured", detail: "AGENT_BASE_URL is not set. See .env.example." },
      { status: 503 },
    );
  }

  // `params` is a Promise in Next 16 — awaiting it is required, not optional.
  const { path } = await params;

  const upstream = await fetch(`${AGENT_BASE_URL}/${path.join("/")}`, {
    method: request.method,
    headers: {
      // Only the two headers that change the response. Forwarding the browser's
      // whole header set would pass along cookies and an Origin the agent has no
      // use for, and `Accept` is the one the streaming protocol reads to decide
      // how to encode events.
      accept: request.headers.get("accept") ?? "application/json",
      "content-type": request.headers.get("content-type") ?? "application/json",
    },
    // GET/HEAD must not carry a body. `duplex: "half"` is required by the fetch
    // spec whenever a body is a stream, which a forwarded request body is.
    body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
    duplex: "half",
    // Next caches fetches by default; a conversation must never be served from
    // cache.
    cache: "no-store",
  } as RequestInit & { duplex: "half" });

  // Returned whole: status, headers, and an unread streaming body.
  return new Response(upstream.body, {
    status: upstream.status,
    headers: upstream.headers,
  });
}

export const GET = proxy;
export const POST = proxy;
