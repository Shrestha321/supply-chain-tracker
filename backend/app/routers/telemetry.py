"""POST /telemetry — ingest endpoint called by the simulator.

Each point does two things in one transaction:
1. appends a row to telemetry_log (the immutable history), and
2. updates the container's current position/status/last_updated (the
   live snapshot the map reads).

Keeping both writes in a single commit means the snapshot can never drift
from the history, even if the process dies mid-request.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..schemas import TelemetryIn, TelemetryOut

router = APIRouter(tags=["telemetry"])


@router.post("/telemetry", response_model=TelemetryOut, status_code=201)
def ingest_telemetry(point: TelemetryIn, db: Session = Depends(get_db)):
    container = db.get(models.Container, point.container_id)
    if container is None:
        raise HTTPException(
            status_code=404, detail=f"container {point.container_id} not found"
        )

    log = models.TelemetryLog(
        container_id=container.id,
        lat=point.lat,
        lng=point.lng,
        temperature=point.temperature,
    )
    if point.timestamp is not None:
        log.timestamp = point.timestamp

    # Update the live snapshot on the container row.
    container.current_lat = point.lat
    container.current_lng = point.lng
    container.last_updated = datetime.now(timezone.utc)
    if point.status is not None:
        container.status = point.status

    db.add(log)
    db.commit()
    db.refresh(log)
    return log
