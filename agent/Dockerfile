# The AI agent service.
#
# WHY THIS IS A SEPARATE IMAGE FROM backend/
# `agent/` has always had its own virtual environment and its own requirements.txt, and
# that separation is deliberate rather than accidental — it is what keeps the AI framework
# out of the backend and the backend's business logic out of the agent. Merging them into
# one image would quietly undo that: every backend container would then carry the AI
# libraries, and the "the agent talks to the ERP over a protocol, not by importing it" rule
# would have no physical boundary left behind it.
#
# Two of the pinned dependencies also only exist here: pydantic-ai-slim and httpx2.
#
# Structure mirrors backend/Dockerfile, which records where the shape comes from (Docker's
# own Python guide and build best-practices page, read 2026-08-26).

# ── Stage 1: install the dependencies ──────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv

# Cache mount: pip's downloads survive between builds without entering the image.
# Bind mount: requirements.txt is handed to this command without becoming a layer, and
# BuildKit still re-runs the step whenever its contents change.
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    /opt/venv/bin/pip install -r requirements.txt

# ── Stage 2: the finished image ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

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

# ⚠️ No `EXPOSE`, and no published port anywhere in the compose file.
#
# agent/app.py sets `HOST = "127.0.0.1"` in code, as a line someone has to deliberately
# delete rather than a flag someone can forget. That line is the reason the agent is safe
# to run without its own token verification yet: it reads a name off a token WITHOUT
# checking the signature (docs/DEPLOY-PLAN.md, "Entry price: the agent-server's own door").
#
# The box does not change it and does not work around it. Every container shares one
# network namespace, so the website reaches the agent on 127.0.0.1:8002 exactly as it does
# on the developer's own machine, and nothing outside the box can reach it at all. Do not
# add an `EXPOSE 8002` here or a `ports:` entry for this service — either one would make
# the deferral in docs/AGENT-PLAN.md expire, and B1 has not been done.
#
# The host and port below must match `HOST` and `PORT` in agent/app.py, which
# agent/tests/test_app.py asserts. They are repeated rather than imported because uvicorn
# is started from the command line here, exactly as the developer starts it locally —
# app.py has no `__main__` block of its own.
CMD ["uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8002"]
