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
# A Docker image is a sealed box containing an operating system, Python, this project's
# dependencies, and the code — everything needed to run, with nothing borrowed from the
# machine it runs on. That is what makes it reproducible on a stranger's laptop.

# python:3.12-slim — "slim" is the small Debian-based variant. Not "alpine": Alpine uses a
# different C library, which means several Python packages have no prebuilt version for it
# and would have to be compiled from source during the build. That turns a two-minute
# build into a twenty-minute one on a judge's machine.
FROM python:3.12-slim

# Two settings that matter specifically inside a container:
#   PYTHONDONTWRITEBYTECODE — don't leave .pyc caches behind; they only bloat the image.
#   PYTHONUNBUFFERED        — print log lines immediately instead of holding them in a
#                             buffer, so `docker compose logs` shows what is happening
#                             while it happens rather than in bursts.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies are copied and installed BEFORE the source code, on purpose. Docker caches
# each step and reuses it while its inputs are unchanged. Requirements change rarely and
# source code changes constantly, so this ordering means an edit to a service file rebuilds
# in seconds instead of reinstalling every package.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as an ordinary user rather than root. If anything ever escapes the application, it
# escapes as a user that owns nothing.
RUN useradd --create-home --uid 10001 aisle \
 && chown -R aisle:aisle /app
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
