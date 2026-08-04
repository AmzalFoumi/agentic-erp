# Third-party notices

Fonts bundled into the production build of this application.

## Why this file exists

`next/font/google` downloads font files **at build time and self-hosts them**, rather than linking to
Google's CDN at runtime. That is deliberate — a runtime `@import` is a render-blocking round trip and
discloses every visitor's IP address to a third party — but it changes the licensing position:
self-hosting means this project **redistributes** the font files, not merely references them.

SIL OFL 1.1 permits that freely, on one condition that applies here: the copyright notice and the
licence must travel with the files. This file is that notice.

Two other OFL conditions, recorded so nobody has to re-derive them: the fonts may not be sold on
their own, and a *modified* version may not be released under a Reserved Font Name. Neither is a
constraint on this project — the fonts are used unmodified, as part of an application.

## Figtree

- Copyright 2022 The Figtree Project Authors
- Designer: Erik Kennedy
- Licence: SIL Open Font License, Version 1.1
- Source: <https://github.com/erikdkennedy/figtree>
- Full licence text: [`licenses/Figtree-OFL.txt`](./licenses/Figtree-OFL.txt)

Used for UI text. Set via `next/font/google` in `src/app/layout.tsx`, exposed as `--font-app-sans`.

## IBM Plex Mono

- Copyright © 2017 IBM Corp.
- Licence: SIL Open Font License, Version 1.1
- Source: <https://github.com/IBM/plex>
- Full licence text: [`licenses/IBM-Plex-OFL.txt`](./licenses/IBM-Plex-OFL.txt)

Used for numeric columns — money, quantities, SKUs — where fixed-width digits are the point rather
than a stylistic preference. Exposed as `--font-app-mono`.

IBM Plex is IBM's corporate typeface, open-sourced by IBM for general use. Using it implies no
affiliation with or endorsement by IBM, and the OFL explicitly forbids suggesting otherwise.

## Everything else

npm dependency licences are not restated here. They are recorded in `package-lock.json` and are not
redistributed as standalone assets the way bundled font files are. If a dependency ever ships an
asset into the build with attribution requirements of its own, it belongs in this file.
