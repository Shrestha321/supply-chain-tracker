"""FastAPI application entrypoint.

Phase 1: health-check only. Phase 2 adds the database connection,
SQLAlchemy models, and the container/telemetry routers.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Supply Chain Container Tracker API",
    description="Tracks shipping containers and predicts delivery delays.",
    version="0.1.0",
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
    """Liveness probe — also used by Render's health check."""
    return {"status": "ok", "phase": 1}
