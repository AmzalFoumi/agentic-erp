"use client";

import { SignedIn, SignedOut, SignInButton, UserDropdown } from "@thunderid/nextjs";

/**
 * Who is signed in, and the way out — the last item in the app header.
 *
 * Kept in `components/shell/` beside DensityToggle and ThemeToggle rather than
 * inlined into `layout.tsx`, for the same reason as those two: the layout says
 * what the header contains, not how any one control behaves.
 *
 * `UserDropdown` reads the user from the ThunderID context — which the server
 * provider has already filled in from `/users/me` — so it needs no props and
 * makes no request of its own on mount. It brings its own sign-out.
 *
 * The `SignedOut` branch is close to unreachable in practice: `src/proxy.ts`
 * protects every route the app serves except `/`, and `/` renders outside this
 * header (see app/layout.tsx). It exists so this component is honest on its own
 * terms, and so a future public page does not silently render a dropdown for
 * nobody.
 */
export function UserMenu() {
  return (
    <>
      <SignedIn>
        <UserDropdown avatarSize={28} />
      </SignedIn>

      <SignedOut>
        {/*
          Leaves the app for ThunderID's hosted sign-in page. That is the
          intended behaviour here, and it depends on
          NEXT_PUBLIC_THUNDERID_SIGN_IN_URL staying *unset*: the SDK checks it
          first and, when set, pushes that local route instead of ever
          requesting an authorize URL.
        */}
        <SignInButton className="text-sm text-muted-foreground hover:text-foreground">
          Sign in
        </SignInButton>
      </SignedOut>
    </>
  );
}
