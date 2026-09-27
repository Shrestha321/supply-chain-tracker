"""Generate the synthetic training set -> data/training_voyages.csv.

There is no real shipping-delay dataset in this hackathon build, so we
encode a plausible ground-truth delay process and sample voyages from it
(spec G explicitly allows synthetic). The formula is deliberately part
linear, part nonlinear:

    delay_hours = 0.02 * weather * remaining_km/100   (weather drag, linear)
                + 20 * congestion^1.5                 (port queue, NONLINEAR)
                + 0.05 * max(0, remaining-8000)/100   (long-route penalty)
                + N(0, 3)                             (noise)

A linear baseline fits the weather term well and the queue term only
approximately — the honest, measurable story for the model comparison.

NO DATABASE REQUIRED: routes come from the static ROUTE_DEFS in
backend/seed.py (route ids = enumeration order, matching what seed.py
creates in any fresh database). That keeps training runnable at Render
build time, where no DB exists yet.

Run:  backend\\.venv\\Scripts\\python.exe prediction\\make_dataset.py [--rows 20000]
"""

import argparse
import csv
import os
import random
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)  # keeps app.config's relative paths sane if anything imports it

from seed import ROUTE_DEFS  # noqa: E402  (static route definitions, no DB access)

import features as F  # noqa: E402  (prediction/ is sys.path[0] when run directly)

DATA = Path(__file__).resolve().parent.parent / "data"


def true_delay_hours(remaining_km: float, weather: float, congestion: float, rng: random.Random) -> float:
    weather_drag = 0.02 * weather * remaining_km / 100.0
    congestion_wait = 20.0 * congestion ** 1.5
    long_route_penalty = 0.05 * max(0.0, remaining_km - 8000.0) / 100.0
    noise = rng.gauss(0.0, 3.0)
    return max(0.0, weather_drag + congestion_wait + long_route_penalty + noise)


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic voyage dataset generator")
    parser.add_argument("--rows", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)

    # Dict-shaped routes mirroring the DB rows seed.py creates:
    # id = enumeration order (1-based), waypoints = [{name, lat, lng}, ...].
    routes = [
        {
            "id": route_id,
            "waypoints": [{"name": n, "lat": la, "lng": lo} for (n, la, lo) in wps],
        }
        for route_id, (_, _, wps) in enumerate(ROUTE_DEFS, start=1)
    ]

    out = DATA / "training_voyages.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(F.FEATURE_COLUMNS + ["delay_hours", "delayed"])
        for _ in range(args.rows):
            route = rng.choice(routes)
            fraction = rng.uniform(0.05, 0.95)          # decision point somewhere mid-voyage
            lat, lng = F.position_at_fraction(route["waypoints"], fraction)
            doy = rng.randint(1, 365)                    # voyage could be any day of the year

            remaining = F.remaining_km_from(route["waypoints"], lat, lng)
            weather = F.weather_severity(route["id"], doy)
            congestion = F.port_congestion(route["id"], doy)
            transit = F.avg_transit_hours(route["waypoints"])

            delay = true_delay_hours(remaining, weather, congestion, rng)
            writer.writerow([
                round(remaining, 1), weather, congestion, round(transit, 1),
                round(delay, 2), int(delay > F.DELAY_THRESHOLD_HOURS),
            ])

    print(f"wrote {args.rows} voyages -> {out} (from {len(routes)} static route definitions)")


if __name__ == "__main__":
    main()
