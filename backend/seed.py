"""Seed the database with routes and containers.

Run from backend/ with the venv python:
    .venv\\Scripts\\python.exe seed.py

Idempotent: skips routes (matched on origin+destination) and containers
(matched on name) that already exist, so it is safe to re-run — including
against Supabase once backend/.env has the real DATABASE_URL.

Writes data/sim_manifest.json: the container->route assignments and starting
progress the simulator needs (so the simulator can stay HTTP-only and never
touch the database directly).
"""

import json
import math
from pathlib import Path

from app.db import SessionLocal
from app.models import Container, Route

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

CONTAINERS_PER_ROUTE = 3
# Starting progress fraction per container within a route. Staggered so the
# map (Phase 5) shows containers spread along each route, not stacked at
# the origin port.
START_FRACTIONS = [0.05, 0.40, 0.70]

# (origin_code, dest_code, [(waypoint_name, lat, lng), ...])
# Intermediate points are approximate shipping-lane positions, not ports.
ROUTE_DEFS = [
    ("CNSHA", "NLRTM", [
        ("Shanghai", 31.23, 121.47),
        ("East China Sea", 27.0, 125.0),
        ("South China Sea", 16.0, 113.0),
        ("Singapore", 1.26, 103.84),
        ("Indian Ocean", 8.0, 80.0),
        ("Arabian Sea", 14.0, 64.0),
        ("Gulf of Aden", 12.5, 47.0),
        ("Red Sea", 20.0, 38.0),
        ("Suez Canal", 30.0, 32.3),
        ("Mediterranean", 36.0, 20.0),
        ("Gibraltar", 36.0, -5.5),
        ("English Channel", 49.5, -1.0),
        ("Rotterdam", 51.95, 4.05),
    ]),
    ("CNSHA", "USLAX", [
        ("Shanghai", 31.23, 121.47),
        ("East China Sea", 30.0, 128.0),
        ("North Pacific", 33.0, 145.0),
        ("North Pacific", 37.0, 165.0),
        ("North Pacific", 40.0, -170.0),
        ("North Pacific", 38.0, -150.0),
        ("North Pacific", 35.0, -130.0),
        ("Los Angeles", 33.74, -118.27),
    ]),
    ("AEJEA", "USNYC", [
        ("Jebel Ali", 25.01, 55.06),
        ("Gulf of Oman", 24.5, 58.5),
        ("Arabian Sea", 17.0, 60.0),
        ("Gulf of Aden", 12.5, 47.0),
        ("Red Sea", 20.0, 38.0),
        ("Suez Canal", 30.0, 32.3),
        ("Mediterranean", 35.5, 20.0),
        ("Central Mediterranean", 36.8, 12.0),
        ("Gibraltar", 36.0, -5.5),
        ("North Atlantic", 38.0, -20.0),
        ("North Atlantic", 38.5, -45.0),
        ("New York/Newark", 40.68, -74.17),
    ]),
    ("NLRTM", "BRSSZ", [
        ("Rotterdam", 51.95, 4.05),
        ("English Channel", 49.5, -1.0),
        ("Bay of Biscay", 45.0, -8.0),
        ("North Atlantic", 38.0, -14.0),
        ("Canary Islands", 28.0, -18.0),
        ("Tropical Atlantic", 15.0, -25.0),
        ("Equatorial Atlantic", 2.0, -35.0),
        ("Brazil Coast", -8.0, -35.0),
        ("Santos", -23.96, -46.33),
    ]),
]


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def cumulative_km(waypoints: list[tuple]) -> list[float]:
    """Cumulative route distance at each waypoint; last element = total."""
    cum = [0.0]
    for i in range(1, len(waypoints)):
        cum.append(cum[-1] + haversine_km(*waypoints[i - 1][1:3], *waypoints[i][1:3]))
    return cum


def position_at_fraction(waypoints: list[tuple], fraction: float) -> tuple[float, float]:
    """Linear-interpolated (lat, lng) at a fraction of total route distance."""
    cum = cumulative_km(waypoints)
    target = max(0.0, min(1.0, fraction)) * cum[-1]
    for i in range(1, len(cum)):
        if target <= cum[i]:
            seg = cum[i] - cum[i - 1]
            t = 0.0 if seg == 0 else (target - cum[i - 1]) / seg
            lat = waypoints[i - 1][1] + t * (waypoints[i][1] - waypoints[i - 1][1])
            lng = waypoints[i - 1][2] + t * (waypoints[i][2] - waypoints[i - 1][2])
            return round(lat, 5), round(lng, 5)
    return waypoints[-1][1], waypoints[-1][2]


def main() -> None:
    ports = json.loads((DATA / "ports.json").read_text(encoding="utf-8"))
    port = {p["code"]: p for p in ports["ports"]}

    db = SessionLocal()
    manifest = []
    try:
        for route_idx, (origin_code, dest_code, waypoints) in enumerate(ROUTE_DEFS, start=1):
            origin, dest = port[origin_code], port[dest_code]
            wp_dicts = [{"name": n, "lat": la, "lng": lo} for (n, la, lo) in waypoints]

            route = (
                db.query(Route)
                .filter_by(origin_port=origin["name"], destination_port=dest["name"])
                .first()
            )
            if route is None:
                route = Route(
                    origin_port=origin["name"],
                    destination_port=dest["name"],
                    waypoints=wp_dicts,
                )
                db.add(route)
                db.flush()  # assigns route.id
                print(f"created route {route.id}: {route.origin_port} -> {route.destination_port}")
            else:
                print(f"route exists (id={route.id}): {route.origin_port} -> {route.destination_port}")

            for j in range(CONTAINERS_PER_ROUTE):
                name = f"CTN-{(route_idx - 1) * CONTAINERS_PER_ROUTE + j + 1:03d}"
                fraction = START_FRACTIONS[j % len(START_FRACTIONS)]
                lat, lng = position_at_fraction(waypoints, fraction)

                container = db.query(Container).filter_by(name=name).first()
                if container is None:
                    container = Container(
                        name=name,
                        current_lat=lat,
                        current_lng=lng,
                        status="at_port" if fraction < 0.02 else "in_transit",
                        route_id=route.id,
                    )
                    db.add(container)
                    db.flush()
                    print(f"  created {name} (id={container.id}) on route {route.id} at {fraction:.0%}")
                else:
                    print(f"  container exists: {name} (id={container.id})")

                manifest.append({
                    "container_id": container.id,
                    "name": name,
                    "route_id": route.id,
                    "start_fraction": fraction,
                })
        db.commit()
    finally:
        db.close()

    manifest_path = DATA / "sim_manifest.json"
    manifest_path.write_text(
        json.dumps({"containers": manifest}, indent=2), encoding="utf-8"
    )
    print(f"manifest written: {manifest_path} ({len(manifest)} containers)")


if __name__ == "__main__":
    main()
