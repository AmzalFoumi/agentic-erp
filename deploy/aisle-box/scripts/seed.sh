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

# Always start from the image's own four databases. Two of them - runtime_persistent and
# runtime_transient - hold sign-in sessions and half-finished login attempts, which belong
# to whoever last used the machine they came from. Those are taken fresh from the image and
# never shipped.
echo "[seed] Laying down the login server's own starting databases."
rm -f /data/*.db /data/*.db-wal /data/*.db-shm
cp -r /opt/thunderid/database/. /data/

# Then overlay Aisle's configuration on top: the applications, resource servers, roles,
# permissions and the `judge` demo account. Only these two files are shipped, and both hold
# passwords as PBKDF2 hashes rather than as readable text - checked before they were
# committed, which is what makes it safe to publish them.
if ls /seed/*.db >/dev/null 2>&1; then
  echo "[seed] Installing Aisle's pre-configured accounts, roles and permissions."
  cp /seed/*.db /data/
else
  echo "[seed] No Aisle configuration found - starting from the login server's defaults."
  echo "[seed] (Expected only while this box is being built; a shipped box has it.)"
fi

touch "$MARKER"
chown -R thunderid:thunderid /data

echo "[seed] Done. Contents of the login-server data folder:"
ls -la /data
