"""In-process background jobs for the deployed API.

Render's free tier runs only web services (no cron jobs, no background
workers), so the two periodic jobs live inside the FastAPI process:

  - telemetry simulation: every SIM_INTERVAL_SECONDS (default 30) each
    container advances SIM_HOURS_PER_TICK (default 3) simulated hours and
    writes a telemetry point THROUGH the real ingest_telemetry handler —
    the same transactional code path as POST /telemetry, no duplication.
    When every voyage completes, containers are reset to their staggered
    starts (seed.seed_all(reset=True)) so the demo loops forever.
  - prediction recompute: every PREDICTION_INTERVAL_SECONDS (default 300)
    appends one predictions row per active container (spec F's polling
    job). The RandomForest bundle is baked into the Render image at build
    time; locally, train it with prediction/train_upgraded.py.

Controlled by RUN_BACKGROUND_JOBS (default false, set true in render.yaml):
local dev runs simulator/simulate.py and prediction/run_predictions.py as
separate processes, and double-posting telemetry would muddy the data.

Both jobs do their blocking work via asyncio.to_thread so the event loop
keeps serving requests. Cross-directory imports (simulator/, prediction/)
work because the repo root is added to sys.path below — on Render the
service root IS the repo root (render.yaml rootDir: .), and locally this
file's location resolves the same way.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("app.jobs")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/app/jobs.py -> repo root
for _p in (str(REPO_ROOT), str(REPO_ROOT / "prediction")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from . import models  # noqa: E402
from .db import SessionLocal  # noqa: E402
from .routers.telemetry import ingest_telemetry  # noqa: E402
from .schemas import TelemetryIn  # noqa: E402


# --------------------------------------------------------------------------
# Telemetry simulation job
# --------------------------------------------------------------------------

def _load_sims():
    """Build simulator state from DB positions, resuming mid-voyage.

    Reuses SimContainer from the standalone HTTP simulator: same movement
    math, same delay events, same restart-safe position projection — the
    in-app job and the external script can never drift apart.
    """
    from simulator.simulate import SimContainer

    db = SessionLocal()
    try:
        routes = {r.id: r for r in db.query(models.Route).all()}
        containers = (
            db.query(models.Container)
            .filter(models.Container.status != "delivered")
            .order_by(models.Container.id)
            .all()
        )
        sims = []
        for c in containers:
            route = routes.get(c.route_id)
            if route is None:
                continue
            sims.append(SimContainer(
                {
                    "id": c.id,
                    "name": c.name,
                    "status": c.status,
                    "current_lat": c.current_lat,
                    "current_lng": c.current_lng,
                },
                {"waypoints": route.waypoints},
            ))
        return sims
    finally:
        db.close()


def _reset_voyages():
    """Demo refresh: reposition every container to its staggered start."""
    from seed import seed_all

    db = SessionLocal()
    try:
        seed_all(db, reset=True, verbose=False)
        db.commit()
        logger.info("all voyages delivered — containers reset for the next demo loop")
    finally:
        db.close()


def _telemetry_tick(sims, hours_per_tick: float):
    """One synchronous tick: advance each container, ingest a point.

    Returns (sims, posted); sims=None means "reload from DB next tick"
    (after a reset).
    """
    if sims is None:
        sims = _load_sims()
        if not sims:
            _reset_voyages()
            sims = _load_sims()

    posted = 0
    db = SessionLocal()
    try:
        for s in sims:
            s.advance(hours_per_tick)
            if s.delivered_posted:
                continue
            lat, lng = s.position()
            point = TelemetryIn(
                container_id=s.id,
                lat=lat,
                lng=lng,
                temperature=s.temperature(lat),
                status=s.status,
            )
            ingest_telemetry(point, db)  # validates + commits, same as the HTTP path
            posted += 1
            if s.status == "delivered":
                s.delivered_posted = True

        if sims and all(s.done for s in sims):
            _reset_voyages()
            sims = None
    finally:
        db.close()
    return sims, posted


async def telemetry_loop():
    interval = float(os.environ.get("SIM_INTERVAL_SECONDS", "30"))
    hours_per_tick = float(os.environ.get("SIM_HOURS_PER_TICK", "3"))
    logger.info("telemetry job: every %.0fs, %.1f simulated hours per tick", interval, hours_per_tick)
    sims = None
    while True:
        try:
            sims, posted = await asyncio.to_thread(_telemetry_tick, sims, hours_per_tick)
            if posted:
                logger.info("telemetry tick: %d points ingested", posted)
        except Exception:
            logger.exception("telemetry tick failed")
        await asyncio.sleep(interval)


# --------------------------------------------------------------------------
# Prediction recompute job
# --------------------------------------------------------------------------

def _load_model_bundle():
    import joblib

    for name in ("model_upgraded.joblib", "model_baseline.joblib"):
        path = REPO_ROOT / "prediction" / name
        if path.exists():
            bundle = joblib.load(path)
            logger.info(
                "prediction model: %s (%s, trained %s)",
                bundle.get("model_kind", "linear_baseline"), name, bundle.get("trained_at", "?"),
            )
            return bundle
    return None


def _prediction_tick(bundle) -> int:
    import pandas as pd
    import features as F  # prediction/ is on sys.path

    db = SessionLocal()
    n = 0
    try:
        routes = {r.id: r for r in db.query(models.Route).all()}
        containers = (
            db.query(models.Container)
            .filter(models.Container.status != "delivered")
            .order_by(models.Container.id)
            .all()
        )
        doy = F.today_doy()

        records = []
        for c in containers:
            route = routes.get(c.route_id)
            if route is None:
                continue
            records.append((c.id, [
                F.remaining_km_from(route.waypoints, c.current_lat, c.current_lng),
                F.weather_severity(route.id, doy),
                F.port_congestion(route.id, doy),
                F.avg_transit_hours(route.waypoints),
            ]))

        if records:
            # Named DataFrame in the trained column order (contract stored
            # in the bundle) — same as prediction/run_predictions.py.
            X = pd.DataFrame([f for _, f in records], columns=bundle["feature_columns"])
            hours_pred = bundle["hours_model"].predict(X)
            prob_pred = bundle["prob_model"].predict_proba(X)[:, 1]
            for (cid, _), h, p in zip(records, hours_pred, prob_pred):
                db.add(models.Prediction(
                    container_id=cid,
                    predicted_delay_hours=round(max(0.0, float(h)), 2),
                    delay_probability=round(float(p), 4),
                ))
                n += 1
            db.commit()
    finally:
        db.close()
    return n


async def prediction_loop():
    interval = float(os.environ.get("PREDICTION_INTERVAL_SECONDS", "300"))
    bundle = await asyncio.to_thread(_load_model_bundle)
    if bundle is None:
        logger.error(
            "no trained model in prediction/ — prediction job disabled "
            "(run prediction/make_dataset.py then prediction/train_upgraded.py)"
        )
        return
    logger.info("prediction job: recomputing every %.0fs", interval)
    while True:
        try:
            n = await asyncio.to_thread(_prediction_tick, bundle)
            logger.info("predictions: wrote %d rows", n)
        except Exception:
            logger.exception("prediction tick failed")
        await asyncio.sleep(interval)


# --------------------------------------------------------------------------

def start_jobs() -> list[asyncio.Task]:
    """Create both job tasks; called from the app lifespan when
    RUN_BACKGROUND_JOBS is true. Caller cancels them on shutdown."""
    # uvicorn configures only its own loggers — without an explicit handler
    # on ours, job INFO lines vanish (no root handler), making the deployed
    # logs useless. Attach one stderr handler, isolated from propagation.
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

    return [
        asyncio.create_task(telemetry_loop(), name="telemetry-job"),
        asyncio.create_task(prediction_loop(), name="prediction-job"),
    ]
