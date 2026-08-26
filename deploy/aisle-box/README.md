# Aisle in a box

Aisle is a supermarket stock and purchasing system with an AI assistant built into it. This
folder runs the whole thing — website, two back-end services, the AI agent, and its own
login server — on your machine with one command.

You do not need to install Python, Node, or a database. You need Docker Desktop, running.

---

## Run it

**1. Put the settings file in place.** The submission includes a file called `aisle.env`.
Copy it into *this* folder and rename it to `.env`:

```bash
cp /path/to/aisle.env deploy/aisle-box/.env
```

**2. Optional — add a Google AI key.** Open that `.env` and paste a key from
[aistudio.google.com/apikey](https://aistudio.google.com/apikey) (free, about a minute)
into the one blank line:

```dotenv
GEMINI_API_KEY=
```

**Leaving it blank is fine, with a caveat.** The whole system still works. The agentic parts stop working, and it tells you
so rather than hanging. 

**3. Start it.**

```bash
docker compose -f deploy/aisle-box/docker-compose.yml up --build
```

The first run builds four images and takes a while — see *How long the first run takes*
below. Later runs skip all of that.

**4. Open [http://localhost:3000](http://localhost:3000) and sign in.**

| | |
|---|---|
| Username | `judge` |
| Password | `AisleDemo2026!` |

That password is written here on purpose. It opens nothing except the copy of the login
server running on your own computer.

---

## The certificate warning, and why you should click through it

The first time your browser is sent to the login server it will say something like *"Your
connection is not private"* or *"Warning: Potential Security Risk Ahead"*.

**This is expected, and here is exactly what it means.** 
This login server generates its own certificate on your machine, on first run, and signs it itself — nobody else vouches for it. Your browser cannot tell "made by
this computer thirty seconds ago" apart from "made by an impostor", so it warns you.

Nothing is leaving your machine. Click **Advanced → Proceed to localhost**.

If you would rather see it for yourself first, open
[https://localhost:8090](https://localhost:8090) directly and accept the warning there.

---

## What's actually running

Six containers. Only two doors are open, and both only to your own machine — nothing on
your network can reach any of it.

| | Address | Open to you? |
|---|---|---|
| The website | `localhost:3000` | **yes** — this is the one you open |
| The login server | `localhost:8090` | **yes** — your browser is redirected here to sign in |
| The web API | `localhost:8000` | no |
| The MCP server (the door the AI uses) | `localhost:8001` | no |
| The AI agent service | `localhost:8002` | no |
| A do-nothing container that owns the network | — | no |

The data lives in a hosted Postgres database, using a login that can read and write exactly
three tables and nothing else.

---

## Things worth trying

1. **Sign in as `judge`** and look at the products list.
2. **Open a product and adjust its stock.** Every change records who made it.
3. **Open the AI panel and ask it something** — "which products are low on stock?" It reads
   the same data through the same rules the website uses, not a separate copy.
4. **Ask it to change something** — "add 20 units to the milk". It will ask you to approve
   before it writes anything.
5. **Watch the permissions.** The AI cannot do anything you cannot do. It acts with a
   narrowed-down version of *your* permissions, not with its own.

---

## Stopping and restarting

```bash
# Stop, keeping everything
docker compose -f deploy/aisle-box/docker-compose.yml stop

# Start again — fast, nothing is rebuilt
docker compose -f deploy/aisle-box/docker-compose.yml start

# Remove the containers, keep the login server's accounts and keys
docker compose -f deploy/aisle-box/docker-compose.yml down

# Throw everything away and start clean next time
docker compose -f deploy/aisle-box/docker-compose.yml down -v
```

`down -v` is safe here: the next `up` rebuilds the login server's data from the files in
this folder. You will get a new administrator password and a new certificate, and `judge`
will still work.

---

## If something goes wrong

**"port is already allocated"** — something else on your machine is already using 3000 or
8090. Stop it, or stop the box and free the port.

**⚠️ Something else is using port 3000 but Docker did NOT complain.** This one is worth
knowing because it looks like a broken box rather than a clash. If another program is
listening on port 3000 over IPv6 (`:::3000`) while the box publishes over IPv4
(`127.0.0.1:3000`), **both succeed** — and your browser, which tries IPv6 first, reaches
the other program. You then see a website that looks like Aisle but fails to sign in.

Check before you conclude anything is wrong with the box:

```bash
# Windows
netstat -ano | findstr :3000
# macOS / Linux
lsof -nP -iTCP:3000 -sTCP:LISTEN
```

Two lines means two programs. Stop the one that is not Docker.

**The website loads but every list is empty** — the database connection string in `.env` is
wrong or the database is asleep. Check with:

```bash
docker compose -f deploy/aisle-box/docker-compose.yml logs api | tail -30
```

**Sign-in bounces back to the start** — usually the certificate warning was never accepted.
Open [https://localhost:8090](https://localhost:8090) directly, accept it, and try again.

**The AI panel errors** — you have no Google AI key, or it is not valid. Everything else
works regardless.

**See what everything is doing:**

```bash
docker compose -f deploy/aisle-box/docker-compose.yml logs -f
```

---

## How long the first run takes

Measured on the developer's machine on 2026-08-26, with everything deleted first
(`down -v`) and the images rebuilt from scratch:

| | |
|---|---|
| Building the four images | **63 seconds** |
| Starting all six containers | **4 seconds** |

**Expect longer than that on your machine, and here is the honest reason.** That measurement
still had the Python and Node package downloads cached locally. Your first run has to fetch
them over the internet, and it also has to download the base images. **Budget five to ten
minutes** depending on your connection. Every run after the first is the 4 seconds.

---

## For the curious

- `docker-compose.yml` — every container, with the reasoning for each in comments.
- `thunderid-seed/` — the login server's pre-made configuration. Every password in it is
  stored as a one-way hash, checked before it was committed.
- `seed-build/` — how that configuration is made. Not needed to run the box.
- `docs/DEPLOY-PLAN.md` in the repository root — the full design, including what this box
  deliberately does *not* do and what would be required to host it for real.
