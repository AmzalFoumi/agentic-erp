"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * Sends a signed-in visitor from `/` to the product list.
 *
 * This used to be a `redirect("/products")` at the top of `src/app/page.tsx`,
 * and then briefly `NEXT_PUBLIC_THUNDERID_AFTER_SIGN_IN_URL=/products`. The
 * second was wrong: that variable is not a landing page. The SDK resolves it to
 * `afterSignInUrl ?? origin` and passes it straight through as the OAuth
 * `redirect_uri`, so a path there fails to match the Authorized Redirect URI
 * registered in the Console and authorization breaks before the login screen
 * renders. It has to stay unset; the redirect has to happen here instead.
 *
 * Client-side and effect-driven rather than a server redirect, because `/` is
 * also the OAuth callback URL: the browser returns to `/?code=...&state=...`
 * and `ThunderIDProvider` completes the exchange after mount. A server-side
 * check would run before the session exists and bounce a valid callback. This
 * component only renders inside `<SignedIn>`, which is decided after that
 * exchange, so by the time the effect fires there is a session.
 *
 * `replace`, not `push`, so Back does not land on a page that immediately
 * redirects forward again.
 */
export function AfterSignInRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/products");
  }, [router]);

  return null;
}
