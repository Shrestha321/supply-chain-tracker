"""Batch inference: append one predictions row per active container.

Spec G: a script that writes to the predictions table — not a live
inference API. Spec F: recomputed periodically — pass --loop SECONDS to
keep it running on an interval (e.g. --loop 300 for every 5 minutes).
On Render (Phase 8) this becomes either a cron job or an in-process
scheduler; the script interface stays the same either way.

Rows are appended, never updated: the API serves the latest row per
container, and history accumulates for free (risk-over-time charts later).

Run:  backend\\.venv\\Scripts\\python.exe prediction\\run_predictions.py [--loop 300]
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)  # so app.config finds backend/.env and relative SQLite paths resolve like uvicorn's

from app.db import SessionLocal  # noqa: E402
from app.models import Container, Prediction, Route  # noqa: E402

import features as F  # noqa: E402  (prediction/ is sys.path[0] when run directly)

BASELINE_PATH = Path(__file__).resolve().parent / "model_baseline.joblib"
UPGRADED_PATH = Path(__file__).resolve().parent / "model_upgraded.joblib"


def run_once(bundle: dict) -> int:
    hours_model = bundle["hours_model"]
    prob_model = bundle["prob_model"]

    db = SessionLocal()
    rows = []
    try:
        routes = {r.id: r for r in db.query(Route).all()}
        containers = (
            db.query(Container)
            .filter(Container.status != "delivered")
            .order_by(Container.id)
            .all()
        )
        doy = F.today_doy()

        records = []
        for c in containers:
            route = routes.get(c.route_id)
            if route is None:
                print(f"  skip {c.name}: route {c.route_id} missing")
                continue
            feats = [
                F.remaining_km_from(route.waypoints, c.current_lat, c.current_lng),
                F.weather_severity(route.id, doy),
                F.port_congestion(route.id, doy),
                F.avg_transit_hours(route.waypoints),
            ]
            records.append((c, feats))

        if records:
            # Build a named DataFrame in the TRAINED column order (stored in
            # the model bundle) — this enforces the feature contract instead
            # of relying on positional luck, and silences sklearn's
            # "no valid feature names" warning. One batched predict call.
            X = pd.DataFrame(
                [feats for _, feats in records],
                columns=bundle["feature_columns"],
            )
            hours_pred = hours_model.predict(X)
            prob_pred = prob_model.predict_proba(X)[:, 1]

            for (c, feats), hours, prob in zip(records, hours_pred, prob_pred):
                hours = max(0.0, float(hours))
                prob = float(prob)
                db.add(Prediction(
                    container_id=c.id,
                    predicted_delay_hours=round(hours, 2),
                    delay_probability=round(prob, 4),
                ))
                rows.append((c.name, c.status, feats[0], hours, prob))

        db.commit()
    finally:
        db.close()

    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] wrote {len(rows)} predictions")
    for name, status, remaining, hours, prob in rows:
        print(f"  {name}  {status:<10} remaining {remaining:8.0f} km  delay {hours:5.1f} h  p {prob:.2f}")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch delay-prediction writer")
    parser.add_argument("--loop", type=int, default=0, metavar="SECONDS",
                        help="rerun every SECONDS (0 = run once and exit)")
    parser.add_argument("--model", choices=["auto", "baseline", "upgraded"], default="auto",
                        help="auto (default) = upgraded RandomForest if trained, else linear baseline")
    args = parser.parse_args()

    model_path = {
        "baseline": BASELINE_PATH,
        "upgraded": UPGRADED_PATH,
        "auto": UPGRADED_PATH if UPGRADED_PATH.exists() else BASELINE_PATH,
    }[args.model]
    if not model_path.exists():
        raise SystemExit(
            f"{model_path} not found — run prediction/make_dataset.py "
            "then train_baseline.py and/or train_upgraded.py first"
        )
    bundle = joblib.load(model_path)
    kind = bundle.get("model_kind", "linear_baseline")
    print(f"model: {kind} ({model_path.name}), trained at {bundle['trained_at']} on {bundle['n_rows']} voyages")

    if args.loop:
        while True:
            run_once(bundle)
            time.sleep(args.loop)
    else:
        run_once(bundle)


if __name__ == "__main__":
    main()
