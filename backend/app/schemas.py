"""Pydantic request/response schemas.

Why these matter: they are the API's validation boundary. Bad input
(lat=999, status="exploded", wrong types) is rejected with a 422 and a
precise error before any DB code runs — the simulator can't corrupt the
tables even when buggy.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Kept in sync with the status values the seed script and simulator use.
ALLOWED_STATUSES = ("in_transit", "at_port", "delayed", "delivered")


class TelemetryIn(BaseModel):
    """Payload for POST /telemetry."""

    container_id: int
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    temperature: float | None = Field(default=None, ge=-40, le=60)
    status: str | None = Field(
        default=None,
        pattern="^(in_transit|at_port|delayed|delivered)$",
        description="When provided, also updates containers.status",
    )
    timestamp: datetime | None = Field(
        default=None,
        description="Client-side event time; defaults to server 'now'",
    )


class TelemetryOut(BaseModel):
    """A telemetry_log row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    container_id: int
    lat: float
    lng: float
    temperature: float | None
    timestamp: datetime


class RouteOut(BaseModel):
    """A routes row. waypoints = ordered [{name, lat, lng}, ...]."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    origin_port: str
    destination_port: str
    waypoints: list
