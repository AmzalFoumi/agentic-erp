#!/bin/sh
# Teach a Python container to trust the login server's certificate, then start the real
# program. Used as the entrypoint for the API and the MCP server.
#
# THE PROBLEM, in plain terms. A certificate is a small file that proves "this really is
# the login server, not an impostor". The login server makes its own on first run, and
# signs it itself. Nothing on the internet vouches for it, so by default every program
# here refuses to talk to it — which is exactly the behaviour we want to keep, because the
# alternative that used to be in this project was switching certificate checking OFF.
#
# THE FIX. Docker mounts that certificate into this container at /certs/server.cert. This
# script writes a combined list of trusted certificates to /tmp; docker-compose.yml points
# SSL_CERT_FILE at that file. Certificate checking stays on.
#
# ⚠️ WHY IT MERGES RATHER THAN REPLACES. SSL_CERT_FILE does not *add* a certificate — it
# *replaces* the whole list. Pointing it straight at /certs/server.cert would leave this
# container trusting the login server and nothing else on the internet. That happens to be
# survivable today, and would break the first time anyone adds an outward HTTPS call. So
# the file written below is: every certificate the operating system already trusts, plus
# this one.
#
# ⚠️ WHY SSL_CERT_FILE IS SET IN docker-compose.yml AND NOT HERE. A variable exported by
# this script exists only for the program it starts. `docker compose exec` opens a brand
# new process that never runs this script, so anything checked that way would appear to
# fail while the running service was perfectly fine — which is exactly the false alarm that
# happened while this was being built. Declaring it in the compose file makes it true for
# every process in the container, including diagnostics.
#
# /tmp is used because the container runs as an ordinary user that owns nothing else.
set -e

BUNDLE=/tmp/aisle-ca-bundle.crt
SYSTEM=/etc/ssl/certs/ca-certificates.crt

if [ -f /certs/server.cert ]; then
  cat "$SYSTEM" /certs/server.cert > "$BUNDLE"
  echo "[ca] Trusting the login server's certificate, with certificate checking left ON."
else
  # Still write the file, because SSL_CERT_FILE names it either way and pointing that at a
  # missing file would break *every* HTTPS call rather than just the login server's.
  cp "$SYSTEM" "$BUNDLE"
  echo "[ca] /certs/server.cert is missing - starting anyway, but any call to the login"
  echo "[ca] server will fail its certificate check. Did thunderid-setup run?"
fi

# Hand over to the command from the compose file, replacing this shell rather than leaving
# it sitting in the middle. That keeps signals working: `docker compose stop` reaches the
# real program instead of a shell that ignores it.
exec "$@"
