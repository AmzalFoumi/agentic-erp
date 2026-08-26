# seed-build/ — how the box's login-server data is made

**Judges never touch anything in this folder.** It exists so the developer can rebuild
`../thunderid-seed/*.db` when the identity configuration changes, and so the reasoning
behind those two binary files is written down rather than lost.

If you only want to *run* the box, read `../README.md` instead.

## Why the box ships a pre-built database at all

The obvious approach — hand judges the ThunderID export and let them import it — was tried
and rejected. It is an eight-step wizard with four secrets to paste by hand, and it aborts
on the first error while still reporting "Valid / 43 of 43 validated / HTTP 200". The full
account is in `.claude/problems/thunderid-import-aborts-on-first-error.md`.

Shipping the finished database instead means the judge runs one command and signs in. The
login server still generates its own certificate, signing keys and admin password on their
machine — only the *configuration* is pre-made.

## Is it safe to publish these files? Yes, and it was checked rather than assumed

This repository is public, so `../thunderid-seed/*.db` is readable by anyone.

Every credential ThunderID stores is a **PBKDF2 hash** — 600,000 iterations, a different
random salt per entity, a 32-byte key. That was confirmed by recomputing a known admin
password from its stored salt and matching the stored value byte for byte, not by reading
documentation and hoping. So the files hold *proofs* of passwords, never passwords.

It also means nothing in them is encrypted with `crypto.key`, so the fresh `crypto.key` that
`setup.sh` generates on the judge's machine cannot break them.

`scan-seed.py` is the gate in front of every commit. **It has already caught one real leak**
— see below. It **refuses to run** without `box-secrets.json`, rather than skipping the
client-secret check and still reporting success.

## The three scripts

| Script | What it does |
|---|---|
| `prune-config.py` | Turns the developer's export into `aisle-config.yml`: removes personal data and development leftovers, replaces the developer's user with a `judge` placeholder |
| `build-seed.py` | Creates the judge account and imports `aisle-config.yml` into a running throwaway box |
| `scan-seed.py` | Refuses to let anything publishable-unsafe reach the committed `.db` files |

## Rebuilding the seed, start to finish

```bash
# 1. Regenerate the configuration from the developer's export.
python deploy/aisle-box/seed-build/prune-config.py

# 2. Start a completely clean box, and note the admin password it prints.
docker compose -f deploy/aisle-box/docker-compose.yml down -v
docker compose -f deploy/aisle-box/docker-compose.yml up -d
docker compose -f deploy/aisle-box/docker-compose.yml logs thunderid-setup

# 3. Get an admin token. Sign in at https://localhost:8090/console as `admin`, then in the
#    browser console:
#      JSON.parse(sessionStorage.getItem("session_data-instance_0-CONSOLE")).access_token
#    A browser is unavoidable here: the Direct API answers 401 on every administrative path,
#    and the flow API refuses headless initiation for browser-type applications (FES-1010).

# 4. Load the configuration. Without --apply it is a dry run.
python deploy/aisle-box/seed-build/build-seed.py --token "<token>" --apply

# 5. Fold the write-ahead logs into the database files, then copy them out.
docker compose -f deploy/aisle-box/docker-compose.yml stop thunderid
docker run --rm -v aisle-box_thunderid-db:/d alpine:3.21 sh -c \
  "apk add sqlite >/dev/null; for f in configdb entitydb; do \
     sqlite3 /d/\$f.db 'pragma wal_checkpoint(TRUNCATE);'; done"
docker run --rm -v aisle-box_thunderid-db:/d:ro \
  -v "$PWD/deploy/aisle-box/thunderid-seed:/out" alpine:3.21 \
  sh -c 'cp /d/configdb.db /d/entitydb.db /out/'

# 6. Check before committing. This is not optional.
python deploy/aisle-box/seed-build/scan-seed.py

# 7. Prove it from nothing: wipe, restart, and sign in as judge.
docker compose -f deploy/aisle-box/docker-compose.yml down -v
docker compose -f deploy/aisle-box/docker-compose.yml up -d
```

Only `configdb.db` and `entitydb.db` are shipped. The other two databases hold sign-in
sessions and half-finished login attempts and are taken fresh from the image every time —
see `../scripts/seed.sh`.

## Four things that were measured, not assumed

Each of these cost a failed attempt, so they are written down rather than rediscovered.

**1. The import cannot create users.** A run reporting `imported: 27` left the entity table
holding three applications and the built-in admin, and no imported user at all. Users have
to be created with `POST /users`, which also assigns its own id and ignores any id you send.
That is why `build-seed.py` creates the judge account *first* and substitutes the real id
into the configuration before importing.

**2. A partial import still answers HTTP 200.** Read `imported` against `totalDocuments`.
The Console says "Valid" while importing 27 of 40.

**3. Deleting a document does not delete what points at it.** The first seed passed every
check in `prune-config.py` and was still unsafe: the committed `configdb.db` contained the
literal string `Claude Code (thunderid-mcp)`, because the *translation* document carries a
display name per application id and nothing had cleaned those up. `scan-seed.py` caught it.
The pruner now strips role assignments and translation entries together.

**4. `POST /users` does store a password** passed as `attributes.password`, hashed the same
way as every other credential. No direct SQL is needed.

## The demo account

`judge` / `AisleDemo2026!`, holding **AIsle Full Access** — the same six permissions on both
resource servers that the backend checks. The password is public on purpose; it opens
nothing but a copy of the login server running on the reader's own machine.

Proven end to end on a box rebuilt from these files alone: the judge signs in and receives a
token with `iss https://localhost:8090`, `aud https://api.agentic-erp.local`, and
`scope openid product.read product.create product.update stock.adjust`.

⚠️ That last line is the check that matters, and gate 23 is the reason. Asking ThunderID for
a permission that does not exist returns a perfectly valid, correctly-audienced token
carrying **no `scope` claim at all**. An empty scope means *zero* permissions, never
"unspecified, so allow" — so always read the scope that came back.

## box-secrets.json

Generated on the first `--apply` run, **gitignored, and never committed**, and written
owner-only (`0600`, where the operating system honours that). A dry run generates the values
in memory and writes nothing, so it really does leave no trace. It holds the box's own client
secrets and session key — minted fresh, never the developer's real ones. They are worthless
against anything but a copy of the login server on the holder's own machine, but they are
plaintext, so they travel in the separately-delivered `aisle.env`, not in this repository.

Delete it and re-run `build-seed.py` to mint new ones — then rebuild the seed, or the
database and the file will no longer agree.
