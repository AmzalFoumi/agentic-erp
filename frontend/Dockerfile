# The Aisle website.
#
# Built in three stages. A "stage" is a throwaway workspace: only the last one becomes the
# finished image, so the compilers, source code and development dependencies used along
# the way are left behind rather than shipped. The finished image holds the built site and
# nothing else.
#
# ── Where this shape comes from ────────────────────────────────────────────────────────
# The three stages, the base image, the `node` user, the copied folders and the ENV/CMD
# lines follow Next.js's own Docker example (vercel/next.js, examples/with-docker, read
# 2026-08-26) together with Docker's build best-practices page. Two documented departures
# from it are marked ⚠️ below; everything else is the vendor's shape.

# ── Stage 1: install dependencies ──────────────────────────────────────────────────────
# Next 16.3.1 requires Node 20.9 or newer (checked in node_modules/next/package.json).
# Node 22 is the current long-term-support line and is what the developer runs.
#
# "slim" (Debian) rather than "alpine", which is also what Next's own example uses. Alpine
# has a different C library, and on it npm falls back to WebAssembly builds of two
# image/CSS packages — see the note on the install command below.
FROM node:22-slim AS deps
WORKDIR /app

COPY package.json package-lock.json ./

# ⚠️ DEPARTURE 1: `npm install`, not the stricter `npm ci` the vendor example uses. This is
# a worked-around npm bug, not a shortcut.
#
# package-lock.json was generated on Windows. npm recorded the Linux builds of the
# platform-specific packages, but NOT two packages that only Linux needs underneath them:
# @emnapi/core and @emnapi/runtime, which Tailwind's and sharp's WebAssembly variants
# depend on. They appear in the lock file only nested under an unrelated package, never at
# the top level. `npm ci` refuses to run at all when the lock file is incomplete like this
# ("Missing: @emnapi/runtime@1.11.3 from lock file") — on Debian and Alpine alike.
#
# `npm install` still installs the versions the lock file pins; it only reaches the
# registry for what is genuinely missing. So the site built here is the site the developer
# tested, plus the two Linux-only packages.
#
# To restore `npm ci`: regenerate the lock file once inside a Linux container, which
# produces a superset that works on both operating systems, and commit it:
#
#   docker run --rm -v "${PWD}:/w" -w /w node:22-slim npm install --package-lock-only
#
# That is an npm command, so it is the developer's to run.
#
# The cache mount keeps npm's download cache between builds without putting it in the
# image — straight from the vendor example.
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund

# ── Stage 2: build the site ────────────────────────────────────────────────────────────
FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

# These arrive as build arguments rather than as ordinary settings, and the reason is
# specific to Next.js: anything named NEXT_PUBLIC_* is **written into the browser
# JavaScript when the site is built**. It is not read when the site runs. So a value only
# supplied at start-up would simply be missing.
#
# None of the three is a secret. A client ID is a name badge, not a password — OAuth
# publishes it to the browser by design. The matching secret is NOT here; it stays a
# run-time setting, read by server-side code only.
ARG NEXT_PUBLIC_THUNDERID_BASE_URL
ARG NEXT_PUBLIC_THUNDERID_CLIENT_ID
ARG NEXT_PUBLIC_THUNDERID_SCOPES

# ⚠️ DEPARTURE 2: two server-side settings are also needed at build time.
#
# `next build` evaluates every page module while working out which pages are static, and
# src/lib/api/client.ts deliberately throws on start-up if API_BASE_URL is missing
# ("API_BASE_URL is not set..."). That check is a good one — a silently unconfigured client
# is worse — so the build is given the values rather than the check being softened.
#
# Set on this stage only, so they do not reach the finished image and cannot shadow
# whatever the compose file passes at run time.
ARG API_BASE_URL=http://127.0.0.1:8000
ARG AGENT_BASE_URL=http://127.0.0.1:8002

ENV NEXT_PUBLIC_THUNDERID_BASE_URL=$NEXT_PUBLIC_THUNDERID_BASE_URL \
    NEXT_PUBLIC_THUNDERID_CLIENT_ID=$NEXT_PUBLIC_THUNDERID_CLIENT_ID \
    NEXT_PUBLIC_THUNDERID_SCOPES=$NEXT_PUBLIC_THUNDERID_SCOPES \
    API_BASE_URL=$API_BASE_URL \
    AGENT_BASE_URL=$AGENT_BASE_URL

RUN npm run build

# ── Stage 3: the finished image ────────────────────────────────────────────────────────
FROM node:22-slim AS runner
WORKDIR /app

# ⚠️ HOSTNAME is 0.0.0.0, and this is the ONLY service in the box that binds that wide.
#
# The website is the one thing the judge's browser has to reach, so the compose file
# publishes port 3000 to their machine. Docker forwards a published port to the container's
# own network address, not to its loopback — so a site bound to 127.0.0.1 would accept
# nothing from outside and the browser would see a closed port.
#
# The API (8000), the MCP server (8001) and the agent (8002) all stay on 127.0.0.1 and are
# published nowhere. Only this door is open.
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# The official node images already ship a non-root `node` user, so there is no account to
# create — using it is what the vendor example does.
#
# `.next` is created up front and handed to that user because the running server writes its
# cache there; without it the first write fails as a permission error.
RUN mkdir .next && chown node:node .next

# `output: "standalone"` in next.config.ts makes Next work out exactly which files the
# built site actually needs and copy them into .next/standalone, together with a small
# server.js. That folder runs on its own — no `npm install` on the judge's machine, and an
# image far smaller than one carrying all of node_modules.
#
# Two folders it deliberately leaves out and we must copy by hand, because Next expects a
# CDN to serve them in a real deployment and there is no CDN here:
#   public/      — static files (icons and so on)
#   .next/static — the compiled JavaScript and CSS
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

USER node

EXPOSE 3000

CMD ["node", "server.js"]
