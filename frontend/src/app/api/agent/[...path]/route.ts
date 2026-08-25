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
 * **Gate 25: it also carries who you are.** The browser's session cookie is
 * useless to the agent — it is a Next.js session, not an OAuth credential — so
 * this route reads the session's access token and forwards it as a normal
 * `Authorization: Bearer` header. That is the only reason the agent can act as
 * you rather than as an anonymous superuser.
 *
 * The token is not inspected here. `src/proxy.ts` has already established that
 * there is a session, and the ERP verifies the token itself against ThunderID's
 * published keys. A third opinion in the middle would be a third thing to get
 * wrong.
 *
 * Nothing here parses the protocol. The upstream `Response` is returned as-is so
 * the SSE body streams through unbuffered — reading it into a string first would
 * turn a live stream into a single delivery at the end, which is the whole thing
 * the streaming protocol exists to avoid.
 */

import { thunderid } from "@thunderid/nextjs/server";

const AGENT_BASE_URL = process.env.AGENT_BASE_URL;

/**
 * The signed-in person's access token, if there is a session.
 *
 * The third copy of this four-line helper, and deliberately so: `lib/api`
 * owns transport, `lib/auth` owns identity, and this file owns one route. The
 * note on `lib/auth/current-user.ts` said to extract it if a third caller
 * appeared — but the two there are in one directory tree and this one is in
 * `app/`, so sharing it would mean `app/` importing from `lib/auth` for four
 * lines. Left duplicated on purpose; revisit if a fourth appears.
 */
async function accessToken(): Promise<string | undefined> {
  try {
    const { getAccessToken, getSessionId } = await thunderid();
    const sessionId = await getSessionId();
    if (!sessionId) return undefined;
    return await getAccessToken(sessionId);
  } catch (error) {
    // Logged rather than swallowed, for the same reason as in
    // `lib/auth/current-user.ts`: ThunderID being down would otherwise look
    // exactly like a quiet Tuesday. The request continues without a token and
    // the agent answers 401, which is the correct outcome — just an
    // undiagnosable one without this line.
    console.error("[agent-proxy] Could not obtain an access token:", error);
    return undefined;
  }
}

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

  const token = await accessToken();

  const upstream = await fetch(`${AGENT_BASE_URL}/${path.join("/")}`, {
    method: request.method,
    headers: {
      // Only the two headers that change the response. Forwarding the browser's
      // whole header set would pass along cookies and an Origin the agent has no
      // use for, and `Accept` is the one the streaming protocol reads to decide
      // how to encode events.
      accept: request.headers.get("accept") ?? "application/json",
      "content-type": request.headers.get("content-type") ?? "application/json",
      // Gate 25. Conditionally spread: with no session there is simply no
      // header, and the agent answers 401 — rather than a literal
      // "Bearer undefined", which would be refused for the wrong reason and
      // read as a token problem instead of a missing session.
      ...(token ? { authorization: `Bearer ${token}` } : {}),
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
