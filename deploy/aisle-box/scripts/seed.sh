#!/bin/sh
# Put the ready-made login-server data in place. Runs once, then exits.
#
# Runs as root so it can hand the files to the `thunderid` user afterwards.
#
# ⚠️ The guard below is a marker file, NOT an "is this folder empty" check, and that is a
# fix rather than a style choice. Docker copies whatever the image already has at a mount
# point into a brand-new volume, and it does that when the container is *created* — which
# Compose does for every service up front, before any of them run. So on a completely
# fresh machine this folder can already look non-empty by the time this script starts. An
# emptiness check reads that as "already done" and silently skips the real seeding.
set -e

MARKER=/data/.aisle-seeded

if [ -f "$MARKER" ]; then
  echo "[seed] Login-server data already present - leaving it exactly as it is."
  exit 0
fi

if ls /seed/*.db >/dev/null 2>&1; then
  echo "[seed] Installing the pre-configured Aisle login-server data."
  # Clear whatever Docker pre-filled from the image first, including SQLite's sidecar
  # write-ahead-log files - a stale -wal alongside a fresh .db is a corrupt database.
  rm -f /data/*.db /data/*.db-wal /data/*.db-shm
  cp /seed/*.db /data/
else
  echo "[seed] No pre-configured data found - falling back to the image's own default."
  echo "[seed] (Expected only while this box is still being built; a shipped box has it.)"
  cp -r /opt/thunderid/database/. /data/
fi

touch "$MARKER"
chown -R thunderid:thunderid /data

echo "[seed] Done. Contents of the login-server data folder:"
ls -la /data
