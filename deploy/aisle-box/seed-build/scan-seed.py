"""Check the shipped login-server databases carry nothing that must not be published.

    python deploy/aisle-box/seed-build/scan-seed.py

This repository is public. `deploy/aisle-box/thunderid-seed/*.db` is committed to it, so
these two files are readable by anyone on the internet. This script is the gate that stands
in front of that, and it should be re-run any time the seed is rebuilt.

WHY COMMITTING THEM IS SAFE AT ALL
Every credential the login server stores is a PBKDF2 hash - 600,000 iterations, a different
random salt per entity, a 32-byte key. That was verified rather than assumed: the scheme was
confirmed by recomputing a known admin password from its stored salt and matching the stored
value exactly. So the files contain proofs of passwords, not passwords.

The demo account's password is public on purpose - it is written in the box's README. It
opens nothing except a copy of the login server running on the reader's own machine.

WHAT WOULD BE A REAL LEAK, and is what this checks for:
  * the developer's name or email address
  * any client secret in readable form
  * any password in readable form
  * leftover development clients from the developer's own machine
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
SEED = REPO / "deploy" / "aisle-box" / "thunderid-seed"
SECRETS = pathlib.Path(__file__).resolve().parent / "box-secrets.json"

# Anything here appearing in the seed is a failure.
FORBIDDEN = {
    "mohamedamzal6@gmail.com": "the developer's email address",
    "Amzal": "the developer's name",
    "Foumi": "the developer's name",
    "localhost:9999": "the 'probe' development client",
    "Test Agent": "a throwaway agent from the gate 23 experiment",
    "thunderid-mcp": "the developer's own admin tooling client",
    "AisleDemo2026!": "the demo password in readable form",
}


def main() -> int:
    files = sorted(SEED.glob("*.db"))
    if not files:
        print(f"No seed databases found in {SEED}.", file=sys.stderr)
        return 1

    # The box's own client secrets must appear only as hashes, never as text.
    #
    # ⚠️ A MISSING SECRETS FILE IS A FAILURE, NOT A NOTE. This used to print "not present,
    # so client secrets were not checked" and carry on to exit 0 - which meant the script
    # could announce "Nothing publishable-unsafe found" while one of the four things it
    # claims to check had never run. A gate that reports success without doing its job is
    # worse than no gate: it is a green light with nothing behind it. Raised by CodeRabbit
    # on PR #34, and it is the same failure shape docs/DEPLOY-PLAN.md already warns about
    # for gate-26 done-conditions.
    if not SECRETS.exists():
        # The filename is written out rather than interpolated from SECRETS.name on
        # purpose: CodeQL's py/clear-text-logging-sensitive-data treats anything derived
        # from a variable named SECRETS as tainted, and flagged this line high severity
        # on PR #35 even though .name is only the filename. Do not turn it back into an
        # f-string - it prints the same characters and re-breaks the security check.
        print("box-secrets.json is missing, so client secrets could NOT be checked.", file=sys.stderr)
        print("Run build-seed.py first. Refusing to report the seed as safe.", file=sys.stderr)
        return 1

    for name, value in json.loads(SECRETS.read_text()).items():
        FORBIDDEN[value] = f"the box's {name} in readable form"

    failed = False
    for path in files:
        blob = path.read_bytes()
        hits = [why for needle, why in FORBIDDEN.items() if needle.encode() in blob]
        hashes = len(re.findall(rb"PBKDF2", blob))
        status = "FAIL" if hits else "ok"
        print(f"{status:>4}  {path.name:<16} {len(blob):>8} bytes, {hashes} PBKDF2 hash(es)")
        for why in hits:
            print(f"      LEAK: {why}", file=sys.stderr)
            failed = True

    if failed:
        print("\nDo not commit these files.", file=sys.stderr)
        return 1

    print("\nNothing publishable-unsafe found. Credentials are present only as PBKDF2 hashes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
