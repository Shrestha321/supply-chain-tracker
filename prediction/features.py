"""Shared feature computation for the prediction pipeline.

Imported by BOTH the training-set generator (make_dataset.py) and batch
inference (run_predictions.py) so training and serving can never drift
apart — training/serving feature skew is the classic silent ML bug.

Weather severity and port congestion are MOCKED here (deterministic
pseudo-random per route+day; congestion seasonal), per spec section G.
Phase 8 swaps the mocks for OpenWeatherMap pulls without changing the
model interface.
"""

import math
import random
import zlib
from datetime import datetime, timezone

SHIP_SPEED_KMH = 34.0          # same assumption as the simulator
PORT_HOURS = 12.0              # fixed handling/port time added per voyage
DELAY_THRESHOLD_HOURS = 6.0    # "delayed" = arriving at least this many hours late

FEATURE_COLUMNS = [
    "distance_remaining_km",
    "weather_severity",
    "port_congestion",
    "avg_transit_hours",
]


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


def route_total_km(waypoints: list[dict]) -> float:
    return cumulative_km(waypoints)[-1]


def position_at_fraction(waypoints: list[dict], fraction: float) -> tuple[float, float]:
    """Interpolated (lat, lng) at a fraction of total route distance."""
    cum = cumulative_km(waypoints)
    target = max(0.0, min(1.0, fraction)) * cum[-1]
    for i in range(1, len(cum)):
        if target <= cum[i]:
            seg = cum[i] - cum[i - 1]
            t = 0.0 if seg == 0 else (target - cum[i - 1]) / seg
            lat = waypoints[i - 1]["lat"] + t * (waypoints[i]["lat"] - waypoints[i - 1]["lat"])
            lng = waypoints[i - 1]["lng"] + t * (waypoints[i]["lng"] - waypoints[i - 1]["lng"])
            return lat, lng
    return waypoints[-1]["lat"], waypoints[-1]["lng"]


def remaining_km_from(waypoints: list[dict], lat: float | None, lng: float | None) -> float:
    """Remaining route km from a position, via nearest-segment projection.

    Planar projection onto each segment is accurate enough at waypoint
    scale (segments are hundreds of km; error is a few km) and avoids
    spherical-geometry code a baseline doesn't need.
    """
    if lat is None or lng is None:
        return route_total_km(waypoints)
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


def avg_transit_hours(waypoints: list[dict]) -> float:
    """Historical average transit time for the route (spec G feature).

    v1 derives it from distance at the standard ship speed plus fixed port
    time; Phase 8 can replace it with per-route statistics computed from
    accumulated telemetry.
    """
    return route_total_km(waypoints) / SHIP_SPEED_KMH + PORT_HOURS


def weather_severity(route_id: int, day_of_year: int) -> float:
    """MOCK weather severity in [0, 1], deterministic per (route, day) so
    training data and same-day inference runs see identical values."""
    rng = random.Random(zlib.crc32(f"wx:{route_id}:{day_of_year}".encode()))
    return round(rng.uniform(0.0, 1.0), 4)


def port_congestion(route_id: int, day_of_year: int) -> float:
    """MOCK congestion (spec G: 'random/seasonal factor'): sinusoid with a
    per-route phase plus deterministic daily jitter, clipped to [0, 1]."""
    phase = (route_id * 73) % 365
    seasonal = 0.5 + 0.35 * math.sin(2 * math.pi * ((day_of_year + phase) % 365) / 365)
    jitter = (zlib.crc32(f"cg:{route_id}:{day_of_year}".encode()) % 1000) / 1000 * 0.15 - 0.075
    return round(min(1.0, max(0.0, seasonal + jitter)), 4)


def today_doy() -> int:
    return datetime.now(timezone.utc).timetuple().tm_yday
