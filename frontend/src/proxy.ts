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
 * The routes anyone may see without signing in. **Everything else is
 * protected**, including routes that do not exist yet.
 *
 * ⚠️ **This list is the inverse of what it was until 2026-08-25, and the
 * direction is the entire point.** It used to name the *protected* routes
 * (`/products*`, `/api/agent*`) while the comment here claimed the opposite
 * policy. Naming the protected routes fails **open**: add `/orders` tomorrow,
 * forget to list it, and it renders for anonymous visitors. Naming the public
 * routes fails **closed**: forget, and the new screen demands a session. The
 * old list happened to cover every route that existed, so nothing was actually
 * exposed - but the comment told the next reader that new screens were covered
 * automatically, which was false. Raised by review on PR #29.
 *
 * ⚠️ **`/` is public, and that is load-bearing rather than a convenience.**
 * `protectRoute()` redirects to `config.signInUrl ?? "/"`, and in
 * ThunderID-hosted ("Gate") mode `NEXT_PUBLIC_THUNDERID_SIGN_IN_URL` is unset -
 * so the fallback is `/`. Protecting `/` would make it redirect to itself,
 * forever. `app/page.tsx` is the signed-out landing, and carries the one
 * `<SignInButton>` that leaves for the hosted page. It is also where ThunderID
 * returns the browser after login. Do not remove it from this list.
 *
 * ⚠️ **No `*` here, and that is deliberate.** `createRouteMatcher` compiles
 * each pattern to `^pattern$` - fully anchored (verified in
 * `dist/server/proxy/createRouteMatcher.js`). So `"/"` matches the root and
 * *only* the root. Writing `"/*"` would make every path public and silently
 * disable this file. If a genuinely public sub-page ever appears, add its exact
 * path; do not reach for a wildcard.
 *
 * ⚠️ **If a pattern ever does need a wildcard, it is `*`, NOT `(.*)`.**
 * `createRouteMatcher` escapes every `.` before it expands `*`, so the `(.*)`
 * idiom used throughout the vendor's own JSDoc compiles to a regex that
 * demands a literal dot after the prefix. `/products` and `/products/123` do
 * not match it; only `/products.something` does. With `(.*)` the old matcher
 * returned false for every real request, and route protection was silently a
 * complete no-op. Checked against @thunderid/nextjs 1.0.6 (the latest
 * published release) and against the package source on the SDK repo's `main`
 * on 2026-08-24 - both carry the same behaviour, so there is no fixed version
 * to upgrade to.
 */
const isPublicRoute = createRouteMatcher([
  "/",
  // The AIsle wordmark, rendered on the signed-out landing page itself - see
  // the note above this list on why a genuinely public asset must be added
  // here rather than relying on the matcher's static-asset exclusions.
  "/aisle-wordmark.png",
]);

export default thunderIDProxy(async (thunderid, request) => {
  if (!isPublicRoute(request)) {
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
  //
  // Note the interaction with the fail-closed list above: anything served from
  // `public/` that is NOT covered by these exclusions now requires a session.
  // Today that is only the five unused `create-next-app` SVGs, which nothing in
  // `src/` references. If a genuinely public asset is ever added - an og:image,
  // a logo on the signed-out landing page - it must be added to `isPublicRoute`
  // or it will 302 to `/` and render as a broken image for signed-out visitors.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
