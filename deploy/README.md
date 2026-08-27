# deploy/

Local-development ThunderID setup, driven by `docker-compose.thunderid.yml`. This folder is the
compose "working directory" Docker records for the running container — confirmed via `docker
inspect thunderid-local-thunderid-1` on 2026-08-25, which reports this path as
`com.docker.compose.project.working_dir`.

**⚠️ Local development only.** Nothing here is a deployment story yet. It runs ThunderID as a
single Docker container on `127.0.0.1:8090` for one developer's machine — no orchestration
target (Fly/Render/ECS/etc.), no TLS termination plan beyond the self-signed
`thunderid-server.cert`, no secrets-management story beyond the `thunderid-local_thunderid-secrets`
Docker volume, and no CI/CD wiring. Gate 26 in `docs/PLAN.md` and `docs/AUTH-PLAN.md` cover the
auth workstream; **the actual deploy-to-a-real-environment plan for ThunderID does not exist yet**
and needs its own gate/decision before this project can be hosted anywhere but localhost.

## ⚠️ There are now two stacks, and they fight over ports

Gate 26 added a second, self-contained stack in `deploy/aisle-box/` — the whole system as one
runnable box, with its **own** login server. The two are kept apart by their Compose project
names, so their data can never mix: this one's volumes are `thunderid-local_*`, the box's are
`aisle-box_*`.

What they *do* share is ports. Both want **8090**, and the box also wants **3000**, which
`npm run dev` holds. A port can only be held by one program at a time, so stop this one before
starting the box:

```bash
docker compose -f deploy/docker-compose.thunderid.yml stop
```

⚠️ **And stop `npm run dev` too, which is the trap that actually cost time.** Port 3000
does *not* fail loudly. `next dev` listens on `:::3000` (IPv6) and Docker publishes on
`127.0.0.1:3000` (IPv4), so **both bind successfully** — and a browser, which tries IPv6
first, reaches `next dev`. The symptom is a site that looks right and cannot sign in, because
the dev server is talking to the box's login server with the *developer's* client secret and
gets `invalid_client`. Measured on 2026-08-26; `[HMR] connected` in the browser console is the
giveaway. Check with `netstat -ano | findstr :3000` — two lines means two programs.

⚠️ **`stop`, never `down -v`.** `down -v` against *this* file deletes every account,
application, secret, role and signing key the developer has, with no backup and no tested restore.
`down -v` is correct only against `deploy/aisle-box/` and other throwaway stacks, where the next
`up` rebuilds everything from committed files.

## Switching between the two stacks

Whichever one you want, stop the other first. They fight over ports 3000 and 8090, and the
clash is silent rather than loud (see the warning above).

**Going to the box** — stop dev work first:

```bash
docker compose -f deploy/docker-compose.thunderid.yml stop   # and Ctrl-C your `npm run dev`
docker compose -f deploy/aisle-box/docker-compose.yml up -d
```

**Coming back to dev work** — stop the box first:

```bash
docker compose -f deploy/aisle-box/docker-compose.yml stop
docker compose -f deploy/docker-compose.thunderid.yml start
```

`stop` on the box is enough; `down -v` there is also safe, because everything it holds is
rebuilt from committed files on the next `up`. **The same is not true of the dev stack** —
see the warning above and the next section.

## Restarting either stack does NOT rotate passwords or keys

Worth stating positively, because the opposite was true once and the fear outlived the fix.

**The danger is real in principle.** The vendor's `setup.sh` has no memory: every run mints a new
administrator password and **new JWT signing keys**, which instantly invalidates every token already
issued and signs out everyone. Registrations are untouched — they live in the database volume — but
nothing signed by the old key verifies again.

**It bit this project once**, on 2026-08-16, when a `depends_on` dragged the one-shot setup container
into every `up`. Both stacks are now guarded, by two different mechanisms. Verified 2026-08-27 by
reading the compose files and `docker compose config --services`; no live `up` was run against the
dev stack to test it, deliberately.

| Stack | Guard | Result of a repeat `up -d` |
|---|---|---|
| `docker-compose.thunderid.yml` (dev) | `thunderid-setup` and `thunderid-db-init` are behind `profiles: ["init"]`, and `thunderid` has **no** `depends_on` on them | They are not started at all. Only `thunderid` comes up. |
| `aisle-box/docker-compose.yml` (box) | No profiles, so both one-shots *are* created — but `seed.sh` and `setup-once.sh` each check a **marker file** on the database volume (`.aisle-seeded`, `.aisle-setup-done`) | They start, print "already done — skipping", and exit 0. |

Check it yourself without starting anything:

```bash
docker compose -f deploy/docker-compose.thunderid.yml config --services
# -> thunderid, and nothing else
```

**So `up -d`, `start`, and Docker Desktop's ▶ button are all safe on both stacks**, and `up -d` is
the correct everyday command for the dev server — as its own compose file says.

### What would still rotate the keys

Three things, all of which take deliberate action:

1. **`down -v`.** It destroys the volumes, and the markers live on the database volume precisely so
   that seeding and setup can never get out of step. Next `up` regenerates everything. ⚠️ Against
   the **dev** stack this also destroys every account, role and client secret you have, with no
   backup — see the warning further up. Against the box it is harmless and expected.
2. **Running the init profile again by hand** on the dev stack. `thunderid-db-init` refuses with a
   message and exit code 1 rather than reseeding, so this fails safely.
3. **Deleting a marker file, or removing the `profiles:` keys.** Both guards are one line each.
   If you ever edit those services, this is what you are protecting.

### If you do get signed out anyway

Read the new administrator password from the `thunderid-setup` container's logs — it is printed
there and nowhere else. Then sign in again. Your registrations survived.

## Where your data lives

Three named Docker volumes hold everything that matters — they are separate from the container,
so stopping or removing the container never touches them:

- `thunderid-local_thunderid-db` — the database (users, sessions, etc.)
- `thunderid-local_thunderid-certs` — certificates
- `thunderid-local_thunderid-secrets` — secret keys

A volume is a small virtual hard drive Docker plugs into the container. Deleting the container is
like recycling the computer case — the plugged-in drive survives untouched.

## Safe shutdown (including laptop restart/shutdown)

Shutting down Docker Desktop, or restarting/shutting down the laptop, is **safe** — it stops the
running container the same way turning off a computer stops a program, and does not touch the
volumes above. No special "shutdown sequence" is required; just close Docker Desktop or restart
normally.

**What is NOT safe** (do not run these against this project):

- `docker compose -f deploy/docker-compose.thunderid.yml down -v` — the `-v` deletes the three
  volumes above, destroying the entire identity store with no backup.
- `docker volume rm thunderid-local_thunderid-*`
- `docker compose ... --profile init` on a machine that already has data — see the guard note
  below; it's survivable but still shouldn't be run on purpose.

## Safe restart

The container is set to `restart: unless-stopped`, so Docker Desktop will normally bring it back
up on its own once Docker Desktop itself is running again. But if you've changed
`thunderid-deployment.yaml` or the compose file, an automatic restart **reuses the old settings**
— Docker only re-reads the compose file when it *(re)creates* a container, not on a plain
restart. To be sure the current config is live, from the repo root:

```bash
# Step 0 — start Docker Desktop and wait for it to be fully up.
# The whale icon must stop animating, or `docker ps` must return without error.
# Everything below fails confusingly if Docker is still starting.

# Step 1 — recreate the container with current settings.
docker compose -f deploy/docker-compose.thunderid.yml up -d
```

⚠️ Plain `up -d`. **Never `--profile init`** on an existing machine, and **never `down -v`**.

Since 2026-08-25, `--profile init` is *survivable* rather than destructive: `thunderid-db-init`
refuses to run against a non-empty `/data` and exits 1, and `thunderid-setup` only runs on its
success, so neither reseeds. A `REFUSING TO RESEED` message is the correct, expected outcome —
not an error to "fix" by running `down -v`. The guard is a safety net, not a reason to rely on it;
still don't run `--profile init` on purpose. The correct first-run-only form, if ever needed
again on a fresh machine, is `--profile init up thunderid-setup` (name the service explicitly — a
bare `up` also starts the profile-less `thunderid` server against an unseeded database).

**Step 2 — confirm it actually restarted with current config**, using whatever check matches your
current change (e.g. the DCR probe in the MCP startup checklist memory). If a check that should
pass fails, the most common cause is step 1 not actually running yet, not a deeper problem.

## Related docs

- `docs/AUTH-PLAN.md` — the auth workstream (gates 22–26), provider decision, DCR/loopback
  coupling. As of 2026-08-25 this shutdown/restart flow and the deployment gap above are not yet
  folded into that doc — this README is the interim record.
- `deploy/SEED-REBUILD.md` — how to copy this stack's identity configuration into the demo
  box, for a reader with no prior context. Read it before changing a permission or role: the
  box ships a pre-made copy of the login-server database, and nothing updates it automatically.
