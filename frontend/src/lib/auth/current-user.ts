/**
 * Who is asking. The frontend half of the identity seam.
 *
 * This mirrors `backend/core/actor.py` on purpose. The backend never reads
 * identity out of ambient request state — every service function takes an
 * `actor` parameter, obtained in exactly one place per adapter. The frontend
 * gets the same treatment for the same reason: when a real auth provider
 * arrives, the change is this file, not every call site that needs a token.
 *
 * As of Gate 24 this is real: the id is the OIDC `sub` of whoever is signed in,
 * the same value the backend stamps into `created_by` / `updated_by`. The full
 * reasoning and the verified provider comparison are in `docs/AUTH-PLAN.md` —
 * do not re-litigate the provider choice here.
 *
 * Server-only. When this stops being a constant it will read a session cookie
 * or perform a token exchange, neither of which may happen in the browser.
 */
import "server-only";

// ⚠️ Nothing imports this yet. It is the seam, not live code: the UI currently
// gets the signed-in user from ThunderID's own <SignedIn>/<UserMenu> client
// components, and no server component has needed the identity yet. It exists so
// that when one does — Gate 25 threads the authenticated actor through the agent
// — there is one place that answers "who is this", rather than three.

import { thunderid } from "@thunderid/nextjs/server";

/**
 * A caller, as far as the frontend is concerned.
 *
 * Deliberately smaller than the backend's `Actor`: there is no `can()`, because
 * permission checks are enforced in `backend/services/` and a second definition
 * here would be a business rule living in the UI. The frontend may eventually
 * *hide* an action it knows will be refused, but it never decides the answer.
 */
export interface CurrentUser {
  /**
   * Stable identifier, matching whatever the backend stamps into
   * `created_by` / `updated_by`. A string so it survives a UUID, an OIDC `sub`,
   * or a synthetic name like "system".
   */
  id: string;
}

/**
 * The current caller, or `null` when nobody is signed in.
 *
 * `null` rather than a throw: on every route this app serves, `src/proxy.ts`
 * has already redirected an anonymous visitor to `/`, so a `null` here is
 * a public page or a bug — neither of which a data-loading helper should turn
 * into a 500. Callers decide what to render.
 */
export async function getCurrentUser(): Promise<CurrentUser | null> {
  const token = await accessToken();
  if (!token) return null;

  const sub = subjectOf(token);
  return sub ? { id: sub } : null;
}

/**
 * The access token for the current request, if there is a session.
 *
 * Same helper as `lib/api/client.ts` uses, deliberately duplicated rather than
 * shared: `lib/api` owns transport and `lib/auth` owns identity, and a module
 * imported across that line would make the two depend on each other for four
 * lines of code. If a third caller appears, extract it then.
 */
async function accessToken(): Promise<string | undefined> {
  try {
    const { getAccessToken, getSessionId } = await thunderid();
    const sessionId = await getSessionId();
    if (!sessionId) return undefined;
    return await getAccessToken(sessionId);
  } catch (error) {
    // Logged rather than swallowed. `undefined` here is indistinguishable from
    // "nobody is signed in", and the caller renders the signed-out state for
    // both — which is the right behaviour for a page, and the wrong behaviour
    // for an operator: ThunderID being down would look exactly like a quiet
    // Tuesday. This line is the only signal that the two are different.
    //
    // Note the genuinely absent session does NOT reach here: `getSessionId()`
    // returns falsy and we return above. So anything caught here is a real
    // fault — the provider unreachable, a malformed session cookie — never the
    // ordinary anonymous case, and it does not log on every public request.
    console.error("[auth] Could not obtain an access token:", error);
    return undefined;
  }
}

/**
 * Read the `sub` claim out of a JWT **without verifying it**, and yes, that is
 * safe here — but only because of what this value is allowed to do.
 *
 * The signature is not checked because nothing on this side is an authorization
 * decision. This id labels a screen: "signed in as …". Every question with an
 * answer that matters — may this person edit that product, whose name goes in
 * `updated_by` — is settled in `backend/services/`, against a token the backend
 * verifies itself against ThunderID's JWKS. The SDK makes the same distinction
 * in `SessionManager`: *"Never use the returned payload for authorization."*
 *
 * If this ever starts gating anything, it is wrong, and the fix is to ask the
 * backend rather than to add a verification step here.
 *
 * Hand-decoded rather than reached for a library: `jose` is a transitive
 * dependency of the SDK, not one this app declares, and importing it would
 * quietly couple us to a version we do not control for one `split`.
 */
function subjectOf(token: string): string | undefined {
  try {
    const payload = token.split(".")[1];
    if (!payload) return undefined;
    // base64url -> base64. Node's atob does not do the URL-safe alphabet.
    const json = Buffer.from(payload, "base64url").toString("utf8");
    const sub: unknown = JSON.parse(json).sub;
    return typeof sub === "string" ? sub : undefined;
  } catch {
    return undefined;
  }
}
