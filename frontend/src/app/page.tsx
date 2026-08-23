import { SignInButton } from "@thunderid/nextjs";

/**
 * The signed-out landing page, and the only route the app serves that is not
 * behind `src/proxy.ts`.
 *
 * It has to be public, and for a mechanical reason rather than a product one.
 * `thunderid.protectRoute()` redirects an unauthenticated visitor to
 * `config.signInUrl ?? "/"` — and in ThunderID-hosted ("Gate") mode
 * `NEXT_PUBLIC_THUNDERID_SIGN_IN_URL` is deliberately unset, so that fallback
 * is `/`. Protecting `/` would therefore redirect `/` to itself. See
 * `node_modules/@thunderid/nextjs/dist/server/proxy/thunderIDProxy.js`.
 *
 * So every protected route funnels a signed-out visitor here, and here is the
 * one button that gets them out again. `<SignInButton>` calls the `signIn`
 * server action with an empty payload, which returns ThunderID's authorize URL
 * and hands the browser over to the hosted sign-in page. On the way back the
 * provider in `layout.tsx` reads `code`/`state` off the URL and completes the
 * exchange — which is why the Authorized Redirect URI registered in the Console
 * is the bare origin, with no callback path.
 *
 * The layout renders this inside `<SignedOut>`; a signed-in visitor who lands
 * on `/` sees the app shell around it instead, so the redirect to the product
 * list that used to live in this file is now
 * `NEXT_PUBLIC_THUNDERID_AFTER_SIGN_IN_URL`.
 */
export default function Home() {
  return (
    <div className="flex flex-col items-center gap-stack text-center">
      <h1 className="text-lg font-semibold">Inventory</h1>
      <p className="text-sm text-muted-foreground">
        Sign in to continue.
      </p>
      <SignInButton className="h-control rounded-(--radius) bg-primary px-4 text-sm font-medium text-primary-foreground">
        Sign in
      </SignInButton>
    </div>
  );
}
