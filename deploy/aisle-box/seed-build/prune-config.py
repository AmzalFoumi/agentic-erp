"""Turn the developer's ThunderID export into the configuration the demo box ships.

Run from the repository root:

    python deploy/aisle-box/seed-build/prune-config.py

Input : deploy/thunderid-export/thunderid-config.yml   (never committed - personal data)
Output: deploy/aisle-box/seed-build/aisle-config.yml        (committed - safe to publish)

WHAT THIS REMOVES AND WHY
The export is a snapshot of a real developer's identity server. Three things in it are
development leftovers, and one is a real person:

  * "Test Agent"                    - a throwaway from gate 23's experiment
  * "probe"                         - a throwaway OAuth client (redirect http://localhost:9999/callback)
  * "Claude Code (thunderid-mcp)"   - the developer's own admin tooling; the box has no
                                      admin MCP server and insecure client registration is
                                      switched off, so it could not work anyway
  * the "amzal" user                - a real name and a real email address, which must not
                                      be published in a public repository

WHAT IT REPLACES
Both user documents are dropped, and every reference to the developer's user id becomes the
placeholder __JUDGE_USER_ID__.

⚠️ THE REASON IS A MEASURED FACT, NOT A PREFERENCE: **the import does not create users.**
A run reporting "imported: 27, failed: 1" left the ENTITY table holding the three
applications and the original admin, and no imported user at all. Users have to be created
through `POST /users`, which also assigns its own id and ignores any id you send. So
build-seed.py creates the judge account first and substitutes the id the server hands back.

Leaving the user documents in would be worse than useless: they import "successfully",
create nothing, and then the "AIsle Agent" document fails with `AGT-1039 "Owner not found"`
because its owner does not exist - which aborts the whole run, since the Console's own
import options use `continueOnError: false`.

WHAT IT LEAVES ALONE
Everything else, including the client secret placeholders like
{{.A_ISLE_GATE_CLIENT_SECRET}}. Those are filled in by the import request, not by this
script, so no secret ever passes through this file. The "Product Reader" role stays but
loses its two assignments (they pointed at Test Agent and at the removed user); an
unassigned role is harmless and shows the permission model the project actually built.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
SOURCE = REPO / "deploy" / "thunderid-export" / "thunderid-config.yml"
TARGET = REPO / "deploy" / "aisle-box" / "seed-build" / "aisle-config.yml"

# Documents to drop, identified by (resource_type, name).
DROP = {
    ("agent", "Test Agent"),
    ("application", "probe"),
    ("application", "Claude Code (thunderid-mcp)"),
}

# Ids of everything removed above. Two separate things reference them and both have to be
# cleaned up, or the removal is only half done:
#   * `assignments:` lists inside role documents
#   * the translation document, which carries a display name per application id
#
# ⚠️ The translation entries were missed on the first pass and caught by scan-seed.py: the
# committed configdb.db still contained the literal string "Claude Code (thunderid-mcp)".
# Deleting a document does not delete what points at it.
DROP_IDS = {
    "01a0115a-c366-7a86-9ece-790ead8ab0eb",  # Test Agent
    "01a0344d-0826-7edb-ae6f-f3b2c5017385",  # probe
    "01a0344d-f519-7695-b0ab-07f4ae3bf3a8",  # Claude Code (thunderid-mcp)
}

# The developer's own user id, as it appears throughout the export. Every occurrence
# becomes JUDGE_ID_PLACEHOLDER, which build-seed.py fills in with the real one.
PERSONAL_USER_ID = "01a02d8f-0355-74cd-b102-3b1ab2372d64"

# The order documents are written in, which is the order the server imports them in.
#
# ⚠️ THIS ORDERING IS LOAD-BEARING, not tidiness. The export lists agents first, and the
# import runs with `continueOnError: false`, so it stops at the first document whose
# references do not resolve yet. "AIsle Agent" is owned by the judge user, and with the
# export's own ordering the import died on document 1 of 40 with
# `AGT-1039 "Owner not found"` — having already written 27 of them. Observed, not feared.
#
# Anything not named here keeps its original position, after everything that is.
IMPORT_ORDER = [
    "organization_unit",   # everything belongs to one
    "user_type",           # a user needs its type to exist
    "agent_type",
    "resource_server",     # roles grant permissions on these
    "user",                # kept for completeness; the import never creates users
    "group",
    "application",
    "agent",
    "flow",
    "layout",
    "theme",
    "translation",
    "server_config",
    "role",                # last: assignments point at users, agents and groups
]

# Substituted by build-seed.py with the id `POST /users` actually assigned.
JUDGE_ID_PLACEHOLDER = "__JUDGE_USER_ID__"


def field(doc: str, key: str) -> str | None:
    match = re.search(rf"^{key}: (.*)$", doc, re.M)
    return match.group(1).strip() if match else None


def strip_references(doc: str) -> str:
    """Remove every line that still points at something this script deleted."""
    for dropped in DROP_IDS:
        escaped = re.escape(dropped)
        # `assignments:` entries inside role documents: an id line plus its type line.
        doc = re.sub(rf"^  - id: {escaped}\n    type: .*\n", "", doc, flags=re.M)
        # Display names inside the translation document, e.g.
        #     app.<id>.name: Claude Code (thunderid-mcp)
        doc = re.sub(rf"^ *app\.{escaped}\..*\n", "", doc, flags=re.M)
    return doc


def main() -> int:
    if not SOURCE.exists():
        print(f"Cannot find {SOURCE}.", file=sys.stderr)
        print("That folder is deliberately untracked - it holds the developer's own", file=sys.stderr)
        print("export. Re-export from the ThunderID Console if it is missing.", file=sys.stderr)
        return 1

    docs = SOURCE.read_text(encoding="utf-8").split("\n---\n")
    kept: list[str] = []
    removed: list[str] = []

    for doc in docs:
        rtype, name = field(doc, "resource_type"), field(doc, "name")

        if (rtype, name) in DROP:
            removed.append(f"{rtype} / {name}")
            continue

        if rtype == "user":
            who = "the developer's own account" if field(doc, "id") == PERSONAL_USER_ID else "the built-in admin"
            removed.append(f"user / {who} (the import cannot create users - see the header)")
            continue

        kept.append(strip_references(doc).replace(PERSONAL_USER_ID, JUDGE_ID_PLACEHOLDER))

    def rank(doc: str) -> int:
        rtype = field(doc, "resource_type")
        return IMPORT_ORDER.index(rtype) if rtype in IMPORT_ORDER else len(IMPORT_ORDER)

    kept.sort(key=rank)  # stable, so documents of one type keep their original order
    TARGET.write_text("\n---\n".join(kept), encoding="utf-8")

    print(f"Read    {len(docs)} documents from {SOURCE.name}")
    for line in removed:
        print(f"Removed {line}")
    print(f"Wrote   {len(kept)} documents to {TARGET.relative_to(REPO)}")

    written = TARGET.read_text(encoding="utf-8")
    leftovers = [
        needle
        for needle in (
            "mohamedamzal", "Amzal", "Foumi",              # the developer
            "localhost:9999", "Test Agent", "thunderid-mcp",  # development leftovers
            PERSONAL_USER_ID,
            *DROP_IDS,   # anything still pointing at a document we deleted
        )
        if needle in written
    ]
    if leftovers:
        print(f"\nFAILED: personal or leftover data still present: {leftovers}", file=sys.stderr)
        return 1

    print("\nChecked: no personal data, no development leftovers in the output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
