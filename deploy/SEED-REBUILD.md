# Rebuilding the demo box's login-server data

**Audience: a developer or agent who has never seen this project.** Everything you need is
here. You do not need any prior context, and you should not need to read any other document
to get through it — the links are for *why*, not for *how*.

**Judges never do any of this.** See "Who runs what" at the bottom.

---

## What this is, in plain English

The project ships a demo box: one command, and a judge gets the whole system running on their
own machine. Part of that system is a **login server** — the thing that holds accounts, roles
and permissions. Its brand name is ThunderID.

Setting a login server up by hand is an eight-step wizard with four secrets to paste. So
instead the box ships a **pre-made copy of its database**: two files, `configdb.db` and
`entitydb.db`. The judge's machine starts the login server, finds the accounts already there,
and the judge just signs in.

Those two files are what this document rebuilds.

**You have to rebuild them whenever the identity configuration changes** — a new permission,
a new role, a new application. If you skip it, the box keeps the *old* configuration, and the
symptom is nasty: a judge signs in successfully and then everything quietly fails, because
their access token carries a permission list that no longer matches what the code checks.

> ⚠️ **The single most important fact in this whole document.** Asking the login server for a
> permission that does not exist does **not** return an error. It returns a perfectly valid,
> correctly-addressed token that carries **no permission list at all**. An empty permission
> list means *zero* permissions — never "unspecified, so allow everything". So a missing
> permission fails **silently**. Always read the permissions that actually came back.

---

## The two login servers, and why they fight

There are two separate copies of the login server on the developer's machine.

| | Started by | Holds | Data lives in |
|---|---|---|---|
| **Dev** — the real one you configure | `deploy/docker-compose.thunderid.yml` | The developer's real account, the real agent, real client secrets | volume `thunderid-local_thunderid-db` |
| **Box** — the throwaway | `deploy/aisle-box/docker-compose.yml` | Nothing you care about; wiped and rebuilt every time | volume `aisle-box_thunderid-db` |

They are kept apart by Docker's project name, so one can never overwrite the other's data.

**But they both publish port `127.0.0.1:8090`, and that cannot be changed.** The port is
written into the server's certificate and into every token it issues (`iss
https://localhost:8090`). Move the port and the tokens stop matching what the applications
expect. So only one of the two can run at a time, and the rebuild has to stop the dev one
partway through.

---

## Before you start

**1. The dev login server must be running and fully configured.** Whatever change you are
capturing — a new permission, a new role — must already be done and working there. This
process copies; it does not create.

**2. Do the rebuild once, at the end.** If you are adding three features, add all three
permissions to the dev server first, then rebuild once. Each rebuild costs about twenty
minutes and involves a browser, so three rebuilds is three chances to hit the silent partial
import described below.

**3. Never run `down -v` on the dev server.**

```bash
# ☠️ THIS DESTROYS EVERY ACCOUNT, ROLE AND CLIENT SECRET, WITH NO BACKUP.
docker compose -f deploy/docker-compose.thunderid.yml down -v
```

In real terms: every account gone, every client secret gone, and every application that signs
in through it — the website, the API, the AI agent — broken until you rebuild the whole
identity configuration by hand from memory. There is no undo and no export to restore from.

`stop`, `start` and `up -d` are all safe. `down -v` on the **box** is not only safe but
required — that one is meant to be thrown away.

---

## The rebuild, step by step

Run everything from the **repository root**.

There is a helper script, `deploy/aisle-box/seed-build/rebuild-seed.sh`, that does the
mechanical parts. Two steps need a real browser and cannot be automated, so the script is
split into phases around them. Each phase is described below alongside the manual step it
replaces, so you can also do the whole thing by hand if the script misbehaves.

### Step 1 — Export the configuration from the dev login server

This one is manual — it needs a browser — but it is one button and one paste.

1. Open <https://localhost:8090/console> and sign in as `admin`.
   The password is in `deploy/admin-password.txt` (gitignored — never commit it).
2. Go to **Import / Export → Export Configuration**, or straight to
   <https://localhost:8090/console/export>.
3. Read the **Total Resources** number on that page and write it down. You compare the
   import against it in step 4, and it is the only way to catch a partial import.
4. Open the browser's JavaScript console (F12 → Console) and paste this. It asks the
   server for the configuration and saves it as a real file download:

```js
(async () => {
  const t = JSON.parse(sessionStorage.getItem("session_data-instance_0-CONSOLE")).access_token;
  const body = {};
  for (const k of ["applications","connections","flows","themes","users","organizationUnits",
                   "userTypes","agentTypes","translations","layouts","resourceServers",
                   "roles","groups","agents","serverConfigs"]) body[k] = ["*"];
  const r = await fetch("/export", {method: "POST", body: JSON.stringify(body),
    headers: {Authorization: "Bearer " + t, "Content-Type": "application/json"}});
  if (!r.ok) throw new Error(`Export failed: ${r.status} ${r.statusText}`);
  const j = await r.json();
  if (typeof j.resources !== "string") {
    throw new Error("Export response did not contain resources");
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([j.resources], {type: "text/yaml"}));
  a.download = "thunderid-config.yml";
  document.body.appendChild(a); a.click(); a.remove();
})();
```

5. Move the downloaded file from your Downloads folder to
   `deploy/thunderid-export/thunderid-config.yml`.

It should be roughly 180 KB and its first line should be `# File: Test_Agent.yaml`.

**What that snippet is doing, in plain English.** The Console's own **Export Configuration**
button sends the server a list saying "give me everything of every kind". The server answers
with JSON, and the whole configuration sits inside one field of it called `resources`, as a
single very long string. The snippet sends the same request, pulls that one field out, and
hands it to the browser as a file to save. The page's own export button does *not* save a
file — it only shows the result — which is why the snippet exists.

> **The `deploy/thunderid-export/` folder is gitignored by a single `*` and must stay that
> way.** The export contains the developer's real name and real email address, and this
> repository is public. Delete the copy left in your Downloads folder too.

**Why a browser is unavoidable here.** It was tried without one and does not work: the Direct
API answers `401` on every administrative path, and the flow API refuses to start a headless
sign-in for a browser-type application (error `FES-1010`). The snippet above sidesteps that by
running *inside* an already-signed-in Console tab, borrowing the token that tab is holding —
it does not get you out of signing in by hand.

### Step 2 — Strip the personal data out

```bash
python deploy/aisle-box/seed-build/prune-config.py
```

Reads the export, writes `deploy/aisle-box/seed-build/aisle-config.yml` (which **is**
committed, and is safe to publish).

It removes the developer's real user, three development leftovers (`Test Agent`, the `probe`
OAuth client, and the developer's own admin tooling client), and every reference to them —
including the display-name entries that point at them, which is a trap that leaked once
already. Every reference to the developer's user id becomes the placeholder
`__JUDGE_USER_ID__`.

`aisle-config.yml` is **generated**. Editing it by hand achieves nothing; the next run
overwrites it. Change the dev login server and re-export instead.

### Step 3 — Stop the dev login server, and start a clean box

```bash
docker compose -f deploy/docker-compose.thunderid.yml stop          # frees port 8090

docker compose -f deploy/aisle-box/docker-compose.yml down -v       # safe: this is the throwaway
docker compose -f deploy/aisle-box/docker-compose.yml up -d
docker compose -f deploy/aisle-box/docker-compose.yml logs thunderid-setup
```

That last line prints the **new admin password** for the box. Note it down; you need it in the
next step, and it is regenerated every time.

> Script equivalent: `bash deploy/aisle-box/seed-build/rebuild-seed.sh prepare`
> (does steps 2 and 3, and refuses to continue if the export from step 1 is missing).

### Step 4 — Get an admin token from the box, and load the configuration

Same browser dance as step 1, and unavoidable for the same reason.

1. Open <https://localhost:8090/console> — this is now the **box's** login server, not yours.
2. Sign in as `admin` with the password from step 3.
3. In the browser console, run:

```js
JSON.parse(sessionStorage.getItem("session_data-instance_0-CONSOLE")).access_token
```

4. Copy the string it prints. Then, from the repository root:

```bash
# Dry run first. Writes nothing, touches nothing.
python deploy/aisle-box/seed-build/build-seed.py --token "<paste>"

# Then for real.
python deploy/aisle-box/seed-build/build-seed.py --token "<paste>" --apply
```

**Read the output. Do not trust the exit code.**

> ⚠️ **A partial import still answers `HTTP 200` and still says "Valid".** One run reported
> `imported: 27` out of 40 documents and looked entirely successful. Compare `imported`
> against `totalDocuments` yourself, every time.

The `--apply` run also creates `box-secrets.json` next to the script — the box's own client
secrets, minted fresh, never the developer's real ones. It is gitignored, written
owner-only, and must never be committed. A dry run generates them in memory only and leaves
no trace.

If you delete `box-secrets.json` you must re-run `build-seed.py --apply` **and** redo steps
5–7, or the file and the database will disagree and the box will not sign anyone in.

### Step 5 — Copy the finished database files out

The login server keeps recent writes in a side file (a "write-ahead log") rather than in the
main database. Copying the database without folding those in gives you a file that is missing
the changes you just made. So: stop the server, fold, copy.

```bash
docker compose -f deploy/aisle-box/docker-compose.yml stop thunderid

docker run --rm -v aisle-box_thunderid-db:/d alpine:3.21 sh -c \
  "apk add sqlite >/dev/null; for f in configdb entitydb; do \
     sqlite3 /d/\$f.db 'pragma wal_checkpoint(TRUNCATE);'; done"

docker run --rm -v aisle-box_thunderid-db:/d:ro \
  -v "$PWD/deploy/aisle-box/thunderid-seed:/out" alpine:3.21 \
  sh -c 'cp /d/configdb.db /d/entitydb.db /out/'
```

Only those two files ship. The other two databases hold sign-in sessions and half-finished
login attempts — they belong to whoever last used that machine, and are taken fresh from the
image every time.

### Step 6 — Run the safety scan. This is not optional.

```bash
python deploy/aisle-box/seed-build/scan-seed.py
```

It refuses to run at all without `box-secrets.json`, rather than skipping the client-secret
check and cheerfully reporting success.

**It has already caught one real leak.** A seed that passed every check in the pruner still
contained the literal string `Claude Code (thunderid-mcp)`, because deleting a document does
not delete the display-name entry pointing at it. Do not commit if this fails.

> Script equivalent for steps 4–6:
> `bash deploy/aisle-box/seed-build/rebuild-seed.sh build --token "<paste>"`

### Step 7 — Prove it works from nothing

```bash
docker compose -f deploy/aisle-box/docker-compose.yml down -v
docker compose -f deploy/aisle-box/docker-compose.yml up -d
```

Then open <http://localhost:3000> and sign in as **`judge` / `AisleDemo2026!`**.

That password is public on purpose. It opens nothing except a copy of the login server running
on the reader's own machine.

**Check the token's permission list**, for the reason in the warning at the top of this
document — a signed-in judge with an empty permission list looks fine until they click
something. It should carry `openid` plus every permission the backend checks.

> Script equivalent: `bash deploy/aisle-box/seed-build/rebuild-seed.sh verify`

#### If sign-in fails, check these three things before suspecting the login-server data

This rebuild only touches ThunderID's identity data (the two `.db` files). It never rebuilds
the box's application images or touches your host machine's ports. Three problems that look
like a broken rebuild are actually neither, and all three were hit for real on 2026-08-28:

**1. The box's own images are stale.** If a feature branch changed anything under
`docker-compose.yml`'s `args:` — most commonly `NEXT_PUBLIC_THUNDERID_SCOPES`, a build-time
value baked into the browser bundle, not read at container start — then `up -d` alone will
keep running the *old* image forever. `docker compose up -d` never rebuilds an existing image
on its own; only `--build`, or deleting the image first, does. The symptom is a `401` on
`/oauth2/token` that has nothing to do with permissions or secrets, because the browser bundle
is still requesting the old, incomplete scope list.

Fix — rebuild images before running `verify`, whenever a change touched `docker-compose.yml`'s
`args:` block:

```bash
docker compose -f deploy/aisle-box/docker-compose.yml build web api mcp agent
bash deploy/aisle-box/seed-build/rebuild-seed.sh verify
```

This is not automatic. `rebuild-seed.sh` never passes `--build` to any `docker compose up`
call, on purpose — it exists to manage identity data, not application code, so don't expect it
to catch this for you. Check `docs/DEPLOY-PLAN.md`'s "What a new feature has to update in the
box" checklist any time you touch a scope or another build-time value.

**2. A local dev frontend is squatting on port 3000.** The box publishes port 3000 to
`127.0.0.1` for its own `web` container. If you also have `npm run dev` running on your host
machine (from ordinary frontend work), Windows will let *both* processes bind port 3000 — one
on `0.0.0.0:3000`, one on `127.0.0.1:3000` — and your browser can silently land on the wrong
one. The giveaway is a `[HMR] connected` line in the browser console: that's Next.js
dev-server hot-reload, which a production Docker build never emits. If you see it while testing
the box, you're talking to your local dev server, not the container — and that dev server
points at your *real* dev ThunderID (possibly stopped), so sign-in fails for reasons that have
nothing to do with the box at all.

Fix — find and stop the stray process before testing:

```bash
netstat -ano | grep ":3000" | grep LISTENING
```

Whichever PID is a plain `node.exe` (not a `docker` process) is the local dev server. Stop it
(PowerShell: `Stop-Process -Id <pid> -Force`; Git Bash's `taskkill` needs the slash escaped:
`taskkill //PID <pid> //F`), then retry sign-in.

**3. The admin password is different after every `verify`.** `verify` does a full `down -v` +
`up -d` of the box, which wipes the ThunderID database volume and re-triggers its first-run
setup — a brand-new admin account and password, every single time, unrelated to whatever
password `prepare` printed earlier. Always re-fetch the current one with:

```bash
docker compose -f deploy/aisle-box/docker-compose.yml logs thunderid-setup
```

Don't reuse a password from an earlier phase or an earlier run.

### Step 8 — Put the dev login server back

```bash
docker compose -f deploy/aisle-box/docker-compose.yml down
docker compose -f deploy/docker-compose.thunderid.yml up -d --force-recreate
```

`--force-recreate` is deliberate. Plain `up -d` has been seen to start the container while
its published port never actually binds — `docker port` returns nothing even though the
configuration says `127.0.0.1:8090`. Recreating fixes it, and is safe: the named volume
survives, and the one-time setup step sits behind a Docker profile so no keys are rotated.

Commit `deploy/aisle-box/thunderid-seed/configdb.db`, `entitydb.db`, and
`deploy/aisle-box/seed-build/aisle-config.yml`.

---

## One thing to get right that the scripts cannot check for you

**Some permissions must belong to humans only, and never to the AI agent.**

The system lets an AI agent *propose* changes, which a human then approves. The permission
that approves is `draft.decide`. If the agent ever holds it, it can approve its own proposals
and the entire safety design is gone.

This is easy to get wrong, because it once was. A single role, `AIsle Full Access`, was
assigned to **both** the human and the agent. Adding `draft.decide` to that role would have
handed the agent self-approval **silently, with every test in the repository still passing** —
the tests prove the *code* refuses an actor without the permission, and this would have given
the agent the permission.

So the dev login server now has two roles, and the box must reproduce both:

| Role | Who | Holds `draft.decide`? |
|---|---|---|
| `AIsle Full Access` | humans only | **yes** |
| `AIsle Agent Access` | the AI agent | **no** |

The export carries this over automatically — provided you split the roles in the dev server
*before* adding the human-only permission, so there is never a window where the agent holds
it. Do the same for any future human-only permission. **After a rebuild, open the box's
Console and confirm the agent is not in `AIsle Full Access`.**

---

## Who runs what

**Judges run none of this.** Nothing in `deploy/aisle-box/seed-build/` is theirs. They get:

```bash
bash deploy/aisle-box/scripts/setup-once.sh
docker compose -f deploy/aisle-box/docker-compose.yml up -d
```

…and then sign in. The two `.db` files are already committed, so their machine has the
finished configuration from the first second. Their login server still generates its own
certificate, its own signing keys and its own admin password locally — only the
*configuration* is pre-made, never any secret.

The client secrets the box needs are plaintext and therefore travel in a separately-delivered
`aisle.env` file, never in this repository.

| Folder | Who | For |
|---|---|---|
| `deploy/aisle-box/scripts/` | judges | running the box |
| `deploy/aisle-box/seed-build/` | developer only | rebuilding what the box ships |
| `deploy/thunderid-export/` | developer only | untracked; holds real personal data |

---

## Why the files are safe to publish

This repository is public, so `deploy/aisle-box/thunderid-seed/*.db` is readable by anyone.
That was checked rather than assumed.

Every credential the login server stores is a **PBKDF2 hash** — 600,000 iterations, a
different random salt per entity, a 32-byte key. Confirmed by recomputing a known admin
password from its stored salt and matching the stored value byte for byte. The files hold
*proofs* of passwords, never passwords.

Nothing in them is encrypted with the server's own key either, which is why the fresh key
generated on a judge's machine cannot break them.

---

## Related documents

- `deploy/aisle-box/README.md` — running the box (the judge-facing document)
- `deploy/aisle-box/seed-build/README.md` — the reasoning behind each script
- `deploy/README.md` — the dev login server: starting, stopping, and what not to do to it
- `docs/DEPLOY-PLAN.md` — what a new feature has to update in the box
