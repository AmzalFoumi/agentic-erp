# The backend, as one image that runs as two containers.
#
# WHY ONE IMAGE FOR TWO SERVICES
# `api/` (the web API the website talks to) and `mcp_server/` (the server the AI agent
# talks to) are two front doors onto the same business logic in `services/`. They share
# one source tree and one requirements.txt; the only difference is the command that starts
# them. Building two near-identical images would double the build time and create a way
# for the two halves to drift apart. The compose file starts this image twice with
# different commands instead.
#
# ── Where this shape comes from ────────────────────────────────────────────────────────
# Structure follows Docker's own Python guide (docs.docker.com/guides/python/containerize)
# and its build best-practices page, read 2026-08-26, not from habit:
#   * multi-stage, with the dependencies installed in one stage and copied into the next
#   * dependencies installed into a virtual environment so the second stage copies one
#     folder rather than picking packages out of the system Python
#   * a cache mount for pip's download cache, so a rebuild does not re-download
#   * a bind mount for requirements.txt, so it never becomes a layer of its own
#   * a non-root user created with an explicit UID
#
# ONE DELIBERATE DEPARTURE from that guide: it now recommends Docker Hardened Images
# (`dhi.io/python:3.12`), which need a Docker subscription. This box is built from a public
# repository by people we have never met, so it stays on the Docker Official Image.

# ── Stage 1: install the dependencies ──────────────────────────────────────────────────
#
# "slim" is the smaller Debian-based variant of the official Python image. NOT "alpine":
# the image's own documentation warns that Alpine "does use musl libc instead of glibc and
# friends, so software will often run into issues depending on the depth of their libc
# requirements" — and several packages here would have to be compiled from source, turning
# a two-minute build into a long one on a judge's machine.
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Everything goes into one self-contained folder so the next stage can copy just that.
RUN python -m venv /opt/venv

# The cache mount keeps pip's downloads between builds without putting them in the image.
# The bind mount hands requirements.txt to this one command without copying it in — so the
# file never becomes part of any layer, while BuildKit still re-runs this step whenever its
# contents change.
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    /opt/venv/bin/pip install -r requirements.txt

# ── Stage 2: the finished image ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Two settings that matter specifically inside a container:
#   PYTHONDONTWRITEBYTECODE — don't leave .pyc caches behind; they only bloat the image.
#   PYTHONUNBUFFERED        — print log lines immediately instead of holding them in a
#                             buffer, so `docker compose logs` shows what is happening
#                             while it happens rather than in bursts.
# PATH puts the copied environment first, so `python` and `uvicorn` mean the ones installed
# in the stage above rather than the system ones.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Run as an ordinary user, never root: if anything ever escapes the application, it escapes
# as a user that owns nothing. The account has no password, no home directory and no login
# shell — it exists only to own a running process. Pattern and flags from Docker's own
# Python template (`docker init`).
ARG UID=10001
RUN adduser \
      --disabled-password \
      --gecos "" \
      --home "/nonexistent" \
      --shell "/sbin/nologin" \
      --no-create-home \
      --uid "${UID}" \
      aisle

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=aisle:aisle . .

USER aisle

# The default is the web API. The compose file overrides this for the MCP server.
#
# --host 127.0.0.1 is deliberate and is NOT the usual container advice. Every container in
# the box shares one network namespace (see deploy/aisle-box/docker-compose.yml), so
# 127.0.0.1 is reachable by its sibling containers but by nothing outside the box. The web
# API is not published to the host at all, so binding wider would only widen the exposure
# without making anything work.
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000"]
