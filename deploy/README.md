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

## ⚠️ Restarting the dev stack rotates its passwords and keys

**The symptom, so you recognise it:** you stop the login server on Friday, start it on Monday,
and everything answers `401`. Nothing is broken and nothing is misconfigured — the credentials
simply are not the same ones any more.

**Why.** `deploy/docker-compose.thunderid.yml` includes a one-shot container, `thunderid-setup`,
that runs `setup.sh` and then exits. `setup.sh` does **not** check whether it has run before. Every
time it runs it issues a **new admin password** and regenerates the **TLS certificate**, the **JWT
signing keys** and the **Direct Auth Secret** — even though the named volumes survived untouched.

What that costs, concretely:

- **Any admin password you wrote down is stale.** Read the new one out of the `thunderid-setup`
  container's logs.
- **Every access token already issued stops verifying**, because the key that signed it is gone.
  Anything holding a token — a browser session, a saved `curl`, a running agent — gets `401`.
- **Your registrations survive.** Resource servers, applications, agents and roles live in the
  `thunderid-db` volume, which `setup.sh` never touches. You do not have to set them up again.

Observed 2026-08-16 → 2026-08-17.

### What actually triggers it

This is the part worth internalising, because two commands that sound identical are not:

| Command | Re-runs `setup.sh`? | Effect |
|---|---|---|
| `docker compose ... start` | **No** | Restarts the existing containers. Credentials survive. |
| `docker compose ... up -d` | **Yes** | Recreates the one-shot container, so setup runs again. |
| Docker Desktop's ▶ button | **Yes** | It issues `up`, not `start`. |

This is why "Coming back to dev work" above says `start` and not `up -d` — that is not a stylistic
choice, it is the whole difference. ⚠️ **Starting the stack from the Docker Desktop GUI does the
unsafe one**, so prefer the command line for this stack.

### When you have to use `up -d` anyway

Changing `deploy/thunderid-deployment.yaml` needs `up -d` — a plain `start` will not apply an edited
config. So a config change and a credential rotation come as a pair here; there is no way to get one
without the other. Plan for it: make the change, then re-read the admin password from the
`thunderid-setup` logs and sign in again.

### The advice that follows from all this

**While you are working a gate, leave the dev stack running** rather than stopping it between
sessions. `stop`/`start` is safe, but the fewer full recreations the fewer surprise sign-outs.

None of this applies to `deploy/aisle-box/`. That stack is *meant* to be rebuilt from committed
files, and its judge account is seeded rather than generated, so its password is stable.

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
