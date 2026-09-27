"""Telemetry simulator: moves fake containers along their routes and POSTs
telemetry points to the API, exactly like a real AIS/IoT feed would.

Usage (from anywhere — uses the backend venv's httpx):
    C:\\dev\\supply-chain-tracker\\backend\\.venv\\Scripts\\python.exe ^
        C:\\dev\\supply-chain-tracker\\simulator\\simulate.py --ticks 3 --interval 1

Options:
    --api-url        API base URL           (default http://127.0.0.1:8000)
    --interval       real seconds per tick  (default 5)
    --hours-per-tick simulated hours per tick (default 2)
    --ticks          stop after N ticks     (default 0 = run until all delivered)

Simulation clock: ships move at ~34 km/h (18 knots). Each tick advances
`hours_per_tick` SIMULATED hours while sleeping `interval` real seconds, so
a Shanghai->Rotterdam voyage (~19,000 km, ~24 real days) completes in about
280 ticks ≈ 23 minutes of wall-clock — watchable in a demo.

Prerequisites: the API must be running and backend/seed.py must have been
run (it creates the routes/containers and writes data/sim_manifest.json).
"""

import argparse
import json
import math
import random
import time
from pathlib import Path

import httpx

DATA = Path(__file__).resolve().parent.parent / "data"

SHIP_SPEED_KMH = 34.0            # ~18 knots, typical container ship
PORT_RADIUS_KM = 150.0           # within this of origin/destination => "at_port"
DELAY_CHANCE_PER_TICK = 0.005    # random chance per container per tick of a hold-up
DELAY_HOURS_RANGE = (12.0, 48.0)  # simulated hours a delay event lasts


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def post_with_retry(client: httpx.Client, payload: dict, retries: int = 2) -> httpx.Response:
    """POST /telemetry, retrying transient transport errors.

    httpx pools keep-alive connections; occasionally the server/OS closes
    an idle pooled connection at the exact moment we reuse it, surfacing as
    ReadError/ConnectError (WinError 10054). A real telemetry feed retries
    through these instead of dying — so do we. Retries run on a fresh
    connection from the pool.
    """
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return client.post("/telemetry", json=payload)
        except httpx.TransportError as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    raise last_exc


class SimContainer:
    """In-memory simulation state for one container.

    Duplicated geo helpers (vs backend/seed.py) are deliberate: the
    simulator imports nothing from the backend so it stays a pure HTTP
    client, like a third-party telemetry feed.
    """

    def __init__(self, entry: dict, route: dict):
        self.id = entry["container_id"]
        self.name = entry["name"]
        self.route_id = entry["route_id"]
        self.waypoints = [
            (w["name"], w["lat"], w["lng"]) for w in route["waypoints"]
        ]
        self.cum = [0.0]
        for i in range(1, len(self.waypoints)):
            self.cum.append(
                self.cum[-1] + haversine_km(*self.waypoints[i - 1][1:3], *self.waypoints[i][1:3])
            )
        self.total_km = self.cum[-1]
        self.km = entry.get("start_fraction", 0.0) * self.total_km
        self.status = "at_port" if self.km < PORT_RADIUS_KM else "in_transit"
        self.delay_remaining_h = 0.0
        self.done = False
        self.delivered_posted = False

    def advance(self, hours: float) -> None:
        """Move one tick forward, handling delay events and arrival."""
        if self.done:
            return
        if self.delay_remaining_h > 0:
            self.delay_remaining_h -= hours
            self.status = "delayed" if self.delay_remaining_h > 0 else "in_transit"
            return
        if random.random() < DELAY_CHANCE_PER_TICK:
            self.delay_remaining_h = random.uniform(*DELAY_HOURS_RANGE)
            self.status = "delayed"
            return
        self.km = min(self.km + hours * SHIP_SPEED_KMH, self.total_km)
        if self.km >= self.total_km:
            self.status = "delivered"
            self.done = True
        else:
            near_end = min(self.km, self.total_km - self.km) < PORT_RADIUS_KM
            self.status = "at_port" if near_end else "in_transit"

    def position(self) -> tuple[float, float]:
        """Interpolated (lat, lng) at the current distance along the route."""
        target = self.km
        for i in range(1, len(self.cum)):
            if target <= self.cum[i]:
                seg = self.cum[i] - self.cum[i - 1]
                t = 0.0 if seg == 0 else (target - self.cum[i - 1]) / seg
                lat = self.waypoints[i - 1][1] + t * (self.waypoints[i][1] - self.waypoints[i - 1][1])
                lng = self.waypoints[i - 1][2] + t * (self.waypoints[i][2] - self.waypoints[i - 1][2])
                return round(lat, 5), round(lng, 5)
        return self.waypoints[-1][1], self.waypoints[-1][2]

    def temperature(self, lat: float) -> float:
        """Crude climate model: warm near the equator, cold at latitude,
        plus per-tick noise so the Phase 4 temperature chart isn't flat."""
        base = 30.0 - 0.45 * abs(lat)
        return round(base + random.uniform(-1.5, 1.5), 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Container telemetry simulator")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--interval", type=float, default=5.0, help="real seconds per tick")
    parser.add_argument("--hours-per-tick", type=float, default=2.0, help="simulated hours per tick")
    parser.add_argument("--ticks", type=int, default=0, help="stop after N ticks (0 = until all delivered)")
    args = parser.parse_args()

    manifest_path = DATA / "sim_manifest.json"
    if not manifest_path.exists():
        raise SystemExit(
            f"{manifest_path} not found — run backend/seed.py first (with the API's DB reachable)."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["containers"]

    with httpx.Client(base_url=args.api_url, timeout=10.0) as client:
        resp = client.get("/routes")
        if resp.status_code != 200:
            raise SystemExit(f"GET /routes failed ({resp.status_code}) — is the API running at {args.api_url}?")
        routes = {r["id"]: r for r in resp.json()}

        sims = [SimContainer(e, routes[e["route_id"]]) for e in manifest if e["route_id"] in routes]
        if not sims:
            raise SystemExit("no containers to simulate — check the manifest and routes")
        print(f"simulating {len(sims)} containers on {len(routes)} routes "
              f"({args.hours_per_tick}h per {args.interval}s tick)")

        tick = 0
        while True:
            tick += 1
            posted = 0
            for s in sims:
                s.advance(args.hours_per_tick)
                if s.delivered_posted:
                    continue
                lat, lng = s.position()
                payload = {
                    "container_id": s.id,
                    "lat": lat,
                    "lng": lng,
                    "temperature": s.temperature(lat),
                    "status": s.status,
                }
                try:
                    r = post_with_retry(client, payload)
                except httpx.HTTPError as exc:
                    # Still failing after retries: log and keep the demo
                    # alive rather than crashing the whole feed.
                    print(f"  WARN {s.name}: transport error after retries: {exc}")
                    continue
                if r.status_code == 201:
                    posted += 1
                else:
                    print(f"  WARN {s.name}: HTTP {r.status_code} {r.text[:120]}")
                if s.status == "delivered":
                    s.delivered_posted = True

            active = sum(1 for s in sims if not s.done)
            delayed = sum(1 for s in sims if s.status == "delayed")
            print(f"tick {tick}: posted {posted} points | {active}/{len(sims)} active | {delayed} delayed")

            if active == 0:
                print("all containers delivered — exiting")
                break
            if args.ticks and tick >= args.ticks:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
