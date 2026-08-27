#!/usr/bin/env bash
# Rebuild the demo box's login-server data — the mechanical parts of it.
#
# READ deploy/SEED-REBUILD.md FIRST. This script is a convenience wrapper around a
# process that has two irreducibly manual steps, not a replacement for understanding it.
#
# Two steps need a real browser and cannot be automated:
#   * exporting the configuration out of the dev login server  (before `prepare`)
#   * reading an admin token out of the box's Console          (before `build`)
# The Direct API answers 401 on every administrative path, and the flow API refuses a
# headless sign-in for a browser-type application (FES-1010). Measured, not assumed.
#
# So the work is split into three phases with the browser steps between them:
#
#   bash deploy/aisle-box/seed-build/rebuild-seed.sh prepare
#   bash deploy/aisle-box/seed-build/rebuild-seed.sh build --token "<paste>"
#   bash deploy/aisle-box/seed-build/rebuild-seed.sh verify
#   bash deploy/aisle-box/seed-build/rebuild-seed.sh restore-dev
#
# Run from anywhere; the script finds the repository root itself.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO"

DEV_COMPOSE="deploy/docker-compose.thunderid.yml"
BOX_COMPOSE="deploy/aisle-box/docker-compose.yml"
SEED_BUILD="deploy/aisle-box/seed-build"
EXPORT_YML="deploy/thunderid-export/thunderid-config.yml"
SEED_DIR="deploy/aisle-box/thunderid-seed"
VOLUME="aisle-box_thunderid-db"

# Docker on Windows/Git Bash rewrites arguments that look like paths. Turn that off for
# the two `docker run` calls, which pass container-side paths like /d and /out.
export MSYS_NO_PATHCONV=1

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$*"; }
die()  { printf '\033[31mXX %s\033[0m\n' "$*" >&2; exit 1; }

phase_prepare() {
  say "Checking the export from the dev login server"
  [ -f "$EXPORT_YML" ] || die "$EXPORT_YML is missing.
Export it from the dev Console first — deploy/SEED-REBUILD.md, step 1.
The export is an HTTP response with the YAML inside a 'resources' field, not a file download."

  local age_note
  age_note="$(date -r "$EXPORT_YML" '+%Y-%m-%d %H:%M' 2>/dev/null || echo unknown)"
  echo "Found $EXPORT_YML (last written $age_note)."
  warn "If that is older than the identity change you are trying to ship, stop and re-export."

  say "Stripping personal data out of the export"
  python "$SEED_BUILD/prune-config.py"

  say "Stopping the dev login server so the box can have port 8090"
  # `stop`, never `down -v`: down -v would destroy every real account and client secret.
  docker compose -f "$DEV_COMPOSE" stop

  say "Wiping and starting a clean box"
  # `down -v` IS correct here. This one is the throwaway; the seed must be reproducible
  # from nothing, so anything left over from a previous attempt has to go.
  docker compose -f "$BOX_COMPOSE" down -v
  docker compose -f "$BOX_COMPOSE" up -d

  say "The box's new admin password"
  docker compose -f "$BOX_COMPOSE" logs thunderid-setup

  cat <<'NEXT'

Next, by hand (deploy/SEED-REBUILD.md, step 4):

  1. Open https://localhost:8090/console and sign in as `admin` with the password above.
  2. In the browser console, run:
       JSON.parse(sessionStorage.getItem("session_data-instance_0-CONSOLE")).access_token
  3. Then:
       bash deploy/aisle-box/seed-build/rebuild-seed.sh build --token "<paste>"

NEXT
}

phase_build() {
  local token="${1:-}"
  [ -n "$token" ] || die "build needs --token \"<admin token>\". See deploy/SEED-REBUILD.md step 4."

  say "Dry run — writes nothing"
  python "$SEED_BUILD/build-seed.py" --token "$token"

  warn "Read the output above. A PARTIAL import still answers HTTP 200 and still says 'Valid'."
  warn "Compare 'imported' against 'totalDocuments' yourself."
  read -r -p "Do those two numbers match? Continue for real? [y/N] " reply
  [ "$reply" = "y" ] || [ "$reply" = "Y" ] || die "Stopped at your request. Nothing was written."

  say "Loading the configuration for real"
  python "$SEED_BUILD/build-seed.py" --token "$token" --apply

  say "Folding the write-ahead logs into the database files"
  # Without this the copied files are missing everything just imported: recent writes live
  # in a side file until they are checkpointed back into the main database.
  docker compose -f "$BOX_COMPOSE" stop thunderid
  docker run --rm -v "$VOLUME:/d" alpine:3.21 sh -c \
    "apk add sqlite >/dev/null; for f in configdb entitydb; do \
       sqlite3 /d/\$f.db 'pragma wal_checkpoint(TRUNCATE);'; done"

  say "Copying the two shipped files out"
  # Only these two. The other databases hold sign-in sessions and half-finished login
  # attempts belonging to whoever last used this machine, and are never shipped.
  docker run --rm -v "$VOLUME:/d:ro" -v "$PWD/$SEED_DIR:/out" alpine:3.21 \
    sh -c 'cp /d/configdb.db /d/entitydb.db /out/'
  ls -l "$SEED_DIR"

  say "Safety scan — this is the gate in front of every commit"
  # Has already caught one real leak. Refuses to run without box-secrets.json rather than
  # skipping the client-secret check and reporting success anyway.
  python "$SEED_BUILD/scan-seed.py"

  cat <<'NEXT'

Scan passed. Next:

  bash deploy/aisle-box/seed-build/rebuild-seed.sh verify

NEXT
}

phase_verify() {
  say "Rebuilding the box from nothing, using only the committed files"
  docker compose -f "$BOX_COMPOSE" down -v
  docker compose -f "$BOX_COMPOSE" up -d

  cat <<'NEXT'

Now prove it by hand:

  1. Open http://localhost:3000 and sign in as  judge / AisleDemo2026!
  2. Check the permissions on the token that comes back.

     ⚠️ Asking for a permission that does not exist returns a VALID token carrying NO
     permission list at all — not an error. Empty means zero permissions, never "allow".
     A missing permission fails silently, so read what actually came back.

  3. Open the box Console and confirm the AI agent is in `AIsle Agent Access` and NOT in
     `AIsle Full Access`. The agent must never hold `draft.decide`.

Then put your own login server back:

  bash deploy/aisle-box/seed-build/rebuild-seed.sh restore-dev

NEXT
}

phase_restore_dev() {
  say "Stopping the box"
  docker compose -f "$BOX_COMPOSE" down

  say "Restarting the dev login server"
  # --force-recreate is deliberate: plain `up -d` has been seen to start the container
  # while its published port never binds. Safe — the named volume survives and the
  # one-time setup step sits behind a Docker profile, so no keys are rotated.
  docker compose -f "$DEV_COMPOSE" up -d --force-recreate

  say "Confirming port 8090 actually bound"
  docker compose -f "$DEV_COMPOSE" port thunderid 8090 || \
    warn "No port shown. Try: docker compose -f $DEV_COMPOSE up -d --force-recreate"

  cat <<'NEXT'

Done. Commit:

  deploy/aisle-box/thunderid-seed/configdb.db
  deploy/aisle-box/thunderid-seed/entitydb.db
  deploy/aisle-box/seed-build/aisle-config.yml

Never commit deploy/thunderid-export/ or seed-build/box-secrets.json.

NEXT
}

case "${1:-}" in
  prepare)     phase_prepare ;;
  build)       shift; [ "${1:-}" = "--token" ] && shift; phase_build "${1:-}" ;;
  verify)      phase_verify ;;
  restore-dev) phase_restore_dev ;;
  *)
    sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 1 ;;
esac
