"""Telemetry simulator: moves containers along their routes and POSTs
telemetry points to the API, exactly like a real AIS/IoT feed would.

State comes FROM THE API (GET /routes + GET /containers): each container's
current position is projected onto its route to recover progress, so the
simulator is restart-safe — it resumes wherever the database says the
container is — and it runs against any deployment (local or Render) with
no manifest file and no database access. Delivered containers are skipped;
use backend/seed.py --reset for a fresh demo.

Usage:
    backend\\.venv\\Scripts\\python.exe simulator\\simulate.py                 # local API
    backend\\.venv\\Scripts\\python.exe simulator\\simulate.py --api-url https://<your-api>.onrender.com

Options:
    --api-url        API base URL             (default http://127.0.0.1:8000)
    --interval       real seconds per tick    (default 5)
    --hours-per-tick simulated hours per tick (default 2)
    --ticks          stop after N ticks       (default 0 = until all delivered)

Simulation clock: ships move at ~34 km/h (18 knots). Each tick advances
`hours_per_tick` SIMULATED hours while sleeping `interval` real seconds, so
a Shanghai->Rotterdam voyage (~19,000 km, ~24 real days) completes in about
280 ticks at defaults — watchable in a demo.
"""

import argparse
import math
import random
import time

import httpx

SHIP_SPEED_KMH = 34.0             # ~18 knots, typical container ship
PORT_RADIUS_KM = 150.0            # within this of origin/destination => "at_port"
DELAY_CHANCE_PER_TICK = 0.005     # random chance per container per tick of a hold-up
DELAY_HOURS_RANGE = (12.0, 48.0)  # simulated hours a delay event lasts


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def cumulative_km(waypoints: list[dict]) -> list[float]:
    """Cumulative route distance at each waypoint; last element = total."""
    cum = [0.0]
    for i in range(1, len(waypoints)):
        cum.append(cum[-1] + haversine_km(
            waypoints[i - 1]["lat"], waypoints[i - 1]["lng"],
            waypoints[i]["lat"], waypoints[i]["lng"],
        ))
    return cum


def remaining_km_from(waypoints: list[dict], lat: float | None, lng: float | None) -> float:
    """Remaining route km from a position, via nearest-segment projection
    (same approach as prediction/features.py — duplicated deliberately so
    the simulator stays a standalone HTTP client with zero backend imports).
    """
    if lat is None or lng is None:
        return cumulative_km(waypoints)[-1]
    cum = cumulative_km(waypoints)
    best_remaining = cum[-1]
    best_d = float("inf")
    for i in range(1, len(waypoints)):
        ax, ay = waypoints[i - 1]["lat"], waypoints[i - 1]["lng"]
        bx, by = waypoints[i]["lat"], waypoints[i]["lng"]
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy
        t = 0.0 if seg_len2 == 0 else ((lat - ax) * dx + (lng - ay) * dy) / seg_len2
        t = max(0.0, min(1.0, t))
        px, py = ax + t * dx, ay + t * dy
        d = (lat - px) ** 2 + (lng - py) ** 2
        if d < best_d:
            best_d = d
            traveled = cum[i - 1] + t * (cum[i] - cum[i - 1])
            best_remaining = cum[-1] - traveled
    return max(0.0, best_remaining)


class SimContainer:
    """In-memory simulation state for one container, resumed from the API."""

    def __init__(self, container: dict, route: dict):
        self.id = container["id"]
        self.name = container["name"]
        self.waypoints = route["waypoints"]
        self.cum = cumulative_km(self.waypoints)
        self.total_km = self.cum[-1]
        # Recover progress: project the DB position onto the route.
        remaining = remaining_km_from(self.waypoints, container.get("current_lat"), container.get("current_lng"))
        self.km = self.total_km - remaining
        status = container.get("status", "in_transit")
        # A DB "delayed" status was some earlier run's in-memory event;
        # resume it as moving (new random delays will occur naturally).
        self.status = "in_transit" if status == "delayed" else status
        self.done = self.status == "delivered"
        self.delivered_posted = self.done
        self.delay_remaining_h = 0.0

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
                lat = self.waypoints[i - 1]["lat"] + t * (self.waypoints[i]["lat"] - self.waypoints[i - 1]["lat"])
                lng = self.waypoints[i - 1]["lng"] + t * (self.waypoints[i]["lng"] - self.waypoints[i - 1]["lng"])
                return round(lat, 5), round(lng, 5)
        return self.waypoints[-1]["lat"], self.waypoints[-1]["lng"]

    def temperature(self, lat: float) -> float:
        """Crude climate model: warm near the equator, cold at latitude,
        plus per-tick noise so the temperature chart isn't flat."""
        base = 30.0 - 0.45 * abs(lat)
        return round(base + random.uniform(-1.5, 1.5), 1)


def post_with_retry(client: httpx.Client, payload: dict, retries: int = 2) -> httpx.Response:
    """POST /telemetry, retrying transient transport errors.

    httpx pools keep-alive connections; occasionally the server/OS closes
    an idle pooled connection at the exact moment we reuse it, surfacing as
    ReadError/ConnectError (WinError 10054). A real telemetry feed retries
    through these instead of dying — so do we. Even more relevant against a
    cold-starting free-tier Render API.
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Container telemetry simulator")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--interval", type=float, default=5.0, help="real seconds per tick")
    parser.add_argument("--hours-per-tick", type=float, default=2.0, help="simulated hours per tick")
    parser.add_argument("--ticks", type=int, default=0, help="stop after N ticks (0 = until all delivered)")
    args = parser.parse_args()

    with httpx.Client(base_url=args.api_url, timeout=15.0) as client:
        try:
            routes = {r["id"]: r for r in client.get("/routes").raise_for_status().json()}
            containers = client.get("/containers").raise_for_status().json()
        except httpx.HTTPError as exc:
            raise SystemExit(f"API at {args.api_url} unreachable or errored: {exc}")

        sims, skipped = [], 0
        for c in containers:
            route = routes.get(c.get("route_id"))
            if route is None or c.get("status") == "delivered":
                skipped += 1
                continue
            sims.append(SimContainer(c, route))

        if not sims:
            print(f"nothing to simulate ({skipped} delivered/unrouted containers).")
            print("For a fresh demo: backend/seed.py --reset, then re-run.")
            return

        print(f"simulating {len(sims)} containers ({skipped} skipped), resumed from DB positions "
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
