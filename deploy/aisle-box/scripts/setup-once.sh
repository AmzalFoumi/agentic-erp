#!/bin/sh
# Generate the things that must belong to THIS machine and must never be shipped:
# the TLS certificate, the keys the login server signs tokens with, the encryption key,
# and the administrator password. Runs once, then exits.
#
# ⚠️ Guarded, because the vendor's setup.sh is not safe to run twice. A second run makes
# new signing keys, which instantly invalidates every token already issued and signs out
# anyone who was signed in. It also resets the administrator password to a new random one.
#
# The marker lives on the database volume rather than the certs volume so that one
# `docker compose down -v` clears seeding and setup together - they must never get out of
# step with each other.
#
# The administrator password setup.sh prints below can be ignored: the Aisle demo signs in
# as an ordinary user, and never needs the login server's own admin console.

MARKER=/opt/thunderid/database/.aisle-setup-done

if [ -f "$MARKER" ]; then
  echo "[setup] Keys and administrator account already exist on this machine - skipping."
  exit 0
fi

echo "[setup] First run on this machine. Generating certificates, keys and an admin account."
# ⚠️ BOTH FAILURES MUST STOP THIS SCRIPT, and the second is the easy one to miss. There is
# no `set -e` here, and `echo` below would otherwise hand back a success exit code even if
# the marker was never written - which re-arms the exact rerun the header warns about: new
# signing keys, every issued token invalidated, the admin password reset.
./setup.sh || exit 1
touch "$MARKER" || exit 1
echo "[setup] Done."
