/**
 * Who is asking. The frontend half of the identity seam.
 *
 * This mirrors `backend/core/actor.py` on purpose. The backend never reads
 * identity out of ambient request state — every service function takes an
 * `actor` parameter, obtained in exactly one place per adapter. The frontend
 * gets the same treatment for the same reason: when a real auth provider
 * arrives, the change is this file, not every call site that needs a token.
 *
 * Nothing is authenticated today. `SystemActor` is still the backend's only
 * `Actor` implementation, so this returns the matching hardcoded `"system"`.
 * The full reasoning, the verified provider comparison, and the two conditions
 * that make the deferral expire are in `docs/AUTH-PLAN.md` — do not re-litigate
 * the provider choice here.
 *
 * Server-only. When this stops being a constant it will read a session cookie
 * or perform a token exchange, neither of which may happen in the browser.
 */
import "server-only";

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
 * The current caller.
 *
 * `async` today for a value that is not asynchronous, and that is intentional:
 * every real implementation of this — reading a cookie, validating a token,
 * exchanging one — is async. Making call sites `await` now means adopting a
 * provider does not turn into an async-propagation refactor across every
 * Server Component that touches data.
 */
export async function getCurrentUser(): Promise<CurrentUser> {
  return { id: "system" };
}
