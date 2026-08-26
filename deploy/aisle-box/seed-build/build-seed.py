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

# The certificate is self-signed and issued for `localhost`, so a build tool talking to the
# throwaway stack on this machine has nothing to verify against. Judges never run this.
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


def box_secrets() -> dict[str, str]:
    if SECRETS.exists():
        return json.loads(SECRETS.read_text())
    minted = {
        "A_ISLE_GATE_CLIENT_SECRET": secrets.token_urlsafe(32),
        "A_ISLE_AGENT_CLIENT_SECRET": secrets.token_urlsafe(32),
        "THUNDERID_SECRET": secrets.token_urlsafe(32),
    }
    SECRETS.write_text(json.dumps(minted, indent=2))
    print(f"Minted fresh box-only secrets -> {SECRETS.name} (gitignored)")
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
            "variables": {**VARIABLES_FIXED, **box_secrets()},
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
