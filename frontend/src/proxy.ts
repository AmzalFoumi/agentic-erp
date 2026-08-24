/**
 * Route protection and token refresh, in front of every render.
 *
 * **Why `src/proxy.ts` and not `middleware.ts` or `proxy.ts` at the repo root.**
 * Next 16 deprecated the `middleware` file convention and renamed it to
 * `proxy`; the file must sit *at the same level as `app`*, and this project
 * uses the `src/` layout, so that level is `src/`, not the project root. (The
 * vendor's guide and an earlier note in docs/AUTH-PLAN.md both say "project
 * root" — true only for an app without `src/`.) See
 * `node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/proxy.md`.
 *
 * `thunderIDProxy` does two jobs, and the second is the one that is easy to
 * miss: besides running the handler below, it proactively refreshes the access
 * token when it is near expiry and writes the new session cookie onto *both*
 * the response and the forwarded request headers — so the Server Component
 * rendering this same request already sees the fresh token. Without this file
 * a session would simply stop working an hour in.
 *
 * Nothing here decides *what* a user may do. This is a bouncer at the door:
 * signed in or not. Every permission question is answered by `services/` in the
 * backend, against a token it verifies itself. See docs/AUTH-PLAN.md.
 */
import { createRouteMatcher, thunderIDProxy } from "@thunderid/nextjs/server";

/**
 * Everything the app actually serves, listed explicitly rather than protecting
 * by exclusion. An allow-list of *public* routes fails open when someone adds a
 * screen and forgets to update it; this fails closed.
 *
 * `/api/agent` is here because that route forwards to the agent service - which
 * is privileged, and must not be reachable by an anonymous browser tab just
 * because it happens to live under a different prefix. Gate 25 replaces that
 * blanket check with real delegation; until then, "signed in" is the floor.
 *
 * ⚠️ **`/` is deliberately NOT protected, and this is load-bearing.**
 * `protectRoute()` redirects to `config.signInUrl ?? "/"`, and in
 * ThunderID-hosted ("Gate") mode `NEXT_PUBLIC_THUNDERID_SIGN_IN_URL` is unset -
 * so the fallback is `/`. Listing `/` here would make it redirect to itself.
 * `app/page.tsx` is the signed-out landing instead, and carries the one
 * `<SignInButton>` that leaves for the hosted page.
 *
 * ⚠️ **The patterns end in `*`, NOT `(.*)`, and that is not a style choice.**
 * `createRouteMatcher` escapes every `.` before it expands `*`, so the `(.*)`
 * idiom used throughout the vendor's own JSDoc compiles to a regex that
 * demands a literal dot after the prefix. `/products` and `/products/123` do
 * not match it; only `/products.something` does. With `(.*)` this matcher
 * returned false for every real request, and route protection was silently a
 * complete no-op. The plain `*` glob is the form their implementation
 * actually supports.
 *
 * Checked against @thunderid/nextjs 1.0.6 (the latest published release) and
 * against the package source on the SDK repo's `main` on 2026-08-24 — both
 * carry the same behaviour, so there is no fixed version to upgrade to. The
 * one cost of `*` is that it also matches `/productsfoo`; that over-protects
 * rather than under-protects, which is the safe direction to be wrong in.
 */
const isProtectedRoute = createRouteMatcher([
  "/products*",
  "/api/agent*",
]);

export default thunderIDProxy(async (thunderid, request) => {
  if (isProtectedRoute(request)) {
    // Redirects to `/` when there is no valid session - see the note above on
    // why that is the fallback.
    //
    // ⚠️ The `return` is load-bearing and the vendor's own JSDoc example omits
    // it. `protectRoute()` does not throw and does not short-circuit: it
    // *returns* a redirect Response, and `thunderIDProxy` uses whatever this
    // handler returns, falling back to `NextResponse.next()` on `undefined`.
    // Dropping the `return` therefore lets every protected route render for a
    // signed-out visitor. Verified on 2026-08-24: `/products` answered 200 with
    // the page shell, the Server Component called the API with no token, and
    // only the backend's own 401 kept the data in. Route protection was a
    // no-op.
    return await thunderid.protectRoute();
  }
});

export const config = {
  // Next's standard exclusion set: static assets and the favicon never need a
  // session check, and running one on each would put a cookie read in front of
  // every image request.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
