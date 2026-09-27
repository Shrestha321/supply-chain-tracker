"""FastAPI application entrypoint.

Phase 2: connects to PostgreSQL (Supabase) and creates the four schema
tables on startup. Phases 3-4 add the telemetry-ingest and container
GET routers.

Schema management note: we use Base.metadata.create_all() instead of
Alembic migrations. Rationale for v1: the schema is brand new, so there is
nothing to migrate — create_all is idempotent (it only creates tables that
don't exist yet). The trade-off: create_all will NOT alter an existing
table if we change a column later; we'd drop/recreate in dev or add Alembic
if the schema needs to evolve against live data. Fine for a hackathon.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import models  # noqa: F401 — imports register the tables on Base.metadata
from .db import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup, before the first request is served."""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Supply Chain Container Tracker API",
    description="Tracks shipping containers and predicts delivery delays.",
    version="0.2.0",
    lifespan=lifespan,
)

# The Vercel-deployed frontend runs on a different origin than this API,
# so browsers will block requests unless we explicitly allow the frontend's
# origin. Wildcard for local development; tighten to the real Vercel URL
# before deploying (Phase 8).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    """Liveness probe that also verifies DB connectivity.

    Returns 503 when the database is unreachable so Render's health check
    (and our own debugging) can distinguish "API up but DB down" from "ok".
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": f"{type(exc).__name__}: {exc}"},
        )
    return {"status": "ok", "phase": 2, "database": "connected"}
