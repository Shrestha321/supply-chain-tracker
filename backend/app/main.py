"""FastAPI application entrypoint.

Phase 8 (deployment): Render's free tier runs only web services — no cron
jobs, no background workers — so the periodic jobs moved in-process
(app/jobs.py), enabled by RUN_BACKGROUND_JOBS=true in render.yaml:
telemetry simulation every 30s, prediction recompute every 5 min.

Startup also seeds reference data (idempotent), so a fresh database —
e.g. the first boot of a new Render Postgres — populates itself with
routes and containers and the jobs can start immediately.

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
from .config import settings
from .db import Base, SessionLocal, engine
from .routers import containers as containers_router
from .routers import routes as routes_router
from .routers import telemetry as telemetry_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup, before the first request is served."""
    Base.metadata.create_all(bind=engine)

    # First-boot seeding: idempotent, so a no-op on every later start.
    # Imported lazily: backend/seed.py lives beside the app package and is
    # importable because uvicorn puts the app dir (cwd locally, --app-dir
    # on Render) on sys.path.
    from seed import seed_all

    db = SessionLocal()
    try:
        seed_all(db, verbose=False)
        db.commit()
    finally:
        db.close()

    job_tasks = []
    if settings.run_background_jobs:
        from .jobs import start_jobs

        job_tasks = start_jobs()

    yield

    for task in job_tasks:
        task.cancel()


app = FastAPI(
    title="Supply Chain Container Tracker API",
    description="Tracks shipping containers and predicts delivery delays.",
    version="0.5.0",
    lifespan=lifespan,
)

# The Vercel-deployed frontend runs on a different origin than this API,
# so browsers will block requests unless we explicitly allow the frontend's
# origin. Wildcard for development; tighten to the real Vercel URL after
# the first deploy if desired.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(containers_router.router)
app.include_router(telemetry_router.router)
app.include_router(routes_router.router)


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
    return {"status": "ok", "phase": 8, "database": "connected"}
