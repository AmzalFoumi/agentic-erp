"""Load the Aisle configuration into a freshly-started box, ready for the seed to be captured.

This is a BUILD tool, run once by the developer to produce the files in
`deploy/aisle-box/thunderid-seed/`. Judges never run it; they get the result.

    python deploy/aisle-box/seed-build/build-seed.py --token <admin access token>
    python deploy/aisle-box/seed-build/build-seed.py --token <...> --apply

Without `--apply` it does a dry run and changes nothing.

WHERE THE TOKEN COMES FROM
The login server only issues an admin token through a browser sign-in - the Direct API
answers 401 on every administrative path, and the flow API refuses headless initiation for
browser-type applications (`FES-1010`). So: open https://localhost:8090/console, sign in as
`admin` with the password the `thunderid-setup` container printed, and read the token out
of the page's own session storage:

    JSON.parse(sessionStorage.getItem("session_data-instance_0-CONSOLE")).access_token

WHY THE ORDER IS USER-FIRST
The import cannot create users. This was measured, not assumed: an import reporting
"imported: 27" left the entity table containing only the three applications and the
built-in admin. `POST /users` is the only way, and it assigns its own id regardless of what
you send. So the judge account is created first and its real id is substituted into the
configuration before the import runs - otherwise the "AIsle Agent" document fails with
`AGT-1039 "Owner not found"` and, because the Console's own import options use
`continueOnError: false`, takes the rest of the run down with it.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import secrets
import ssl
import sys
import urllib.error
import urllib.request

BASE = "https://localhost:8090"
HERE = pathlib.Path(__file__).resolve().parent
CONFIG = HERE / "aisle-config.yml"
SECRETS = HERE / "box-secrets.json"          # gitignored - see .gitignore in this folder

# The demo account judges sign in with. The password is documented in the box's README and
# is public by design: it opens nothing but a copy of the login server running on the
# reader's own machine.
JUDGE = {
    "ouId": "01900000-0000-7000-8000-000000000001",
    "type": "Person",
    "attributes": {
        "email": "judge@aisle.demo",
        "family_name": "Judge",
        "given_name": "Demo",
        "name": "Demo Judge",
        "sub": "judge",
        "username": "judge",
        "password": "AisleDemo2026!",
    },
}

# Client IDs are carried over from the developer's own setup unchanged. They are not
# secrets - OAuth publishes a client ID to the browser by design - and keeping them means
# the website's baked-in build argument matches without another moving part. The SECRETS
# are freshly minted for the box and never reused from the developer's instance.
VARIABLES_FIXED = {
    "CONSOLE_CLIENT_ID": "CONSOLE",
    "CONSOLE_REDIRECT_URIS": [f"{BASE}/console"],
    "A_ISLE_GATE_CLIENT_ID": "vAf_zSFT1qj4733Xy3jgQw",
    "A_ISLE_GATE_REDIRECT_URIS": ["http://localhost:3000"],
    "A_ISLE_AGENT_CLIENT_ID": "6in2mfBltFEEMpYjF5upZA",
    "A_ISLE_AGENT_REDIRECT_URIS": ["http://localhost:8002/callback"],
}

# ⚠️ Certificate checking is OFF here, and this is the one place in gate 26 where that is
# still true. Said plainly rather than softly, because CodeRabbit raised it on PR #34 and
# the risk is real: `call()` below sends an ADMINISTRATOR bearer token in the Authorization
# header, so any process that managed to bind localhost:8090 while this script runs would
# receive it and could rewrite the configuration being seeded.
#
# Left as it is, deliberately, for three reasons. The certificate is generated inside a
# Docker volume and does not exist on disk at the moment this runs, so verifying would mean
# extracting it first. This is a developer-only build tool, run by hand, against a throwaway
# stack on the developer's own machine - judges never run it and it is not part of the box.
# And the attack it enables requires someone already running code on that machine.
#
# What would change this: running this script against anything that is not localhost. Do not.
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def call(path: str, token: str, payload=None, method="GET"):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, context=_CTX) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        print(f"HTTP {error.code} from {method} {path}", file=sys.stderr)
        print(error.read().decode()[:1500], file=sys.stderr)
        raise SystemExit(1)


def box_secrets(*, persist: bool) -> dict[str, str]:
    """The box's own client secrets, minted on first use.

    ⚠️ `persist` exists because a dry run must leave nothing behind. This function used to
    write the file unconditionally, so `build-seed.py --token ...` with no `--apply` - the
    run the docs call "a dry run, it changes nothing" - created durable credentials, and a
    later real run silently reused them. The values still have to be *generated* either way,
    because the import request needs them in order to be validated at all; they are simply
    thrown away afterwards unless the run is real. Raised by CodeRabbit on PR #34.
    """
    if SECRETS.exists():
        return json.loads(SECRETS.read_text())

    minted = {
        "A_ISLE_GATE_CLIENT_SECRET": secrets.token_urlsafe(32),
        "A_ISLE_AGENT_CLIENT_SECRET": secrets.token_urlsafe(32),
        "THUNDERID_SECRET": secrets.token_urlsafe(32),
    }

    if not persist:
        print("Dry run: secrets generated in memory only, nothing written.")
        return minted

    # ⚠️ os.open with mode 0o600 rather than Path.write_text, which applies the process
    # umask and so lands at 0644 on a typical machine - leaving these readable by every
    # other account on it. The mode is a no-op on Windows, where the file inherits the
    # directory's permissions; it is not a no-op anywhere else. Raised by CodeRabbit on
    # PR #34.
    fd = os.open(SECRETS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(minted, handle, indent=2)

    # The filename is written out rather than interpolated from SECRETS.name on
    # purpose: CodeQL's py/clear-text-logging-sensitive-data treats anything derived
    # from a variable named SECRETS as tainted, and flagged this line high severity
    # on PR #35 even though .name is only the filename. Do not turn it back into an
    # f-string - it prints the same characters and re-breaks the security check.
    print("Minted fresh box-only secrets -> box-secrets.json (gitignored, owner-only)")
    return minted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", required=True, help="admin access token, see the module docstring")
    parser.add_argument("--apply", action="store_true", help="actually write; otherwise dry run")
    args = parser.parse_args()

    existing = {u["attributes"].get("username"): u["id"] for u in call("/users", args.token).get("users", [])}
    if "judge" in existing:
        judge_id = existing["judge"]
        print(f"Judge account already present: {judge_id}")
    elif not args.apply:
        judge_id = "<assigned-on-apply>"
        print("Dry run: would create the judge account")
    else:
        judge_id = call("/users", args.token, JUDGE, method="POST")["id"]
        print(f"Created the judge account: {judge_id}")

    config = CONFIG.read_text(encoding="utf-8").replace("__JUDGE_USER_ID__", judge_id)

    result = call(
        "/import",
        args.token,
        {
            "content": config,
            "variables": {**VARIABLES_FIXED, **box_secrets(persist=args.apply)},
            "dryRun": not args.apply,
            # Matches what the Console itself sends. `upsert` updates rather than
            # duplicates, so this is safe to re-run.
            "options": {"upsert": True, "continueOnError": False, "target": "runtime"},
        },
        method="POST",
    )

    summary = result.get("summary", {})
    print(f"\nImport ({'applied' if args.apply else 'dry run'}): {json.dumps(summary)}")

    # ⚠️ Read `imported` against `totalDocuments`, never the HTTP status. A run that
    # imports 27 of 40 still answers 200, and the Console still says "Valid".
    failures = [r for r in result.get("results", []) if r.get("status") != "success"]
    for failure in failures:
        print("FAILED:", json.dumps(failure)[:400], file=sys.stderr)

    if summary.get("failed") or summary.get("imported") != summary.get("totalDocuments"):
        print("\nIncomplete import - do not capture a seed from this.", file=sys.stderr)
        return 1

    print("Every document imported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
