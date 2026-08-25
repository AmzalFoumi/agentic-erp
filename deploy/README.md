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
