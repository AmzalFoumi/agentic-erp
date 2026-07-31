"""The FastAPI application. Run with:

    uvicorn api.main:app --reload

from `backend/`, then open http://127.0.0.1:8000/docs.

`api.main:app` names a module and the variable inside it. uvicorn imports the
module and serves whatever `app` refers to - the same shape as pointing a Node
process at an exported Express instance.

### What this file is allowed to contain

Wiring, and nothing else: create the app, install error handlers, add CORS,
include routers, declare /health. If application logic ever appears here it has
skipped both the route layer and the service layer at once.

### Why there is no `lifespan`

Current FastAPI offers a `lifespan` async context manager for startup and
shutdown work, replacing the deprecated `@app.on_event("startup")` you will
still see in most tutorials. We do not need one: the engine in core/database.py
is created at import time and its pool opens connections lazily, so there is
nothing to set up and nothing to tear down. Adding an empty lifespan to look
thorough would be noise. If a background scheduler or a warm-up query ever
arrives, this is where it goes - and it must be `lifespan`, not `on_event`.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from api.deps import DbSession
from api.errors import install_error_handlers
from api.routes import products
from core.config import settings

app = FastAPI(
    title="Supermarket Inventory API",
    version="0.1.0",
    # This description is the front page of the generated /docs.
    description=(
        "HTTP adapter over the shared service layer. Every operation here is "
        "also available as an MCP tool - both call the same functions in "
        "services/, which is where all business rules live."
    ),
)

install_error_handlers(app)

# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------
#
# A browser refuses to let a page on localhost:3000 read a response from
# localhost:8000 unless the server explicitly permits it. The two differ in
# port, which is enough to make them different *origins*. This is a browser
# rule, not an HTTP one - curl and the MCP server are unaffected, which is why
# a request can work in your terminal and fail in the frontend.
#
# The allowed list is explicit rather than `["*"]`. A wildcard is genuinely
# fine while there is no authentication, and genuinely dangerous the moment
# there is: `allow_credentials=True` combined with `*` would let any website a
# logged-in user visits call this API with their cookies attached. Setting the
# habit now means not having to remember later.
#
# The list comes from settings rather than being written here, because it is
# environment-specific: localhost while developing, a real domain once this is
# deployed. See CORS_ORIGINS in core/config.py and .env.example.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)


@app.get("/health", tags=["meta"])
def health(session: DbSession) -> dict[str, str]:
    """Liveness check that actually proves something.

    Returning a hardcoded `{"status": "ok"}` would confirm only that the Python
    process is running - which the response itself already proved. This runs
    `SELECT 1` against Postgres, so a green answer means the app can reach its
    database. That is the failure this endpoint exists to catch: Supabase asleep,
    credentials rotated, network gone.

    `text("SELECT 1")` is required because SQLAlchemy 2.0 refuses to execute a
    bare string. It is a deliberate speed bump against accidentally passing a
    formatted string - the shortest path to SQL injection - so raw SQL has to be
    marked as intentional.
    """
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}
