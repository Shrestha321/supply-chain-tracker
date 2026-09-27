"""Container read endpoints (spec section F).

- GET /containers                       — list all with current status
- GET /containers/{id}                  — detail + bounded telemetry history
- GET /containers/{id}/prediction       — latest delay prediction

Query design notes:
- The list endpoint eager-loads routes with joinedload(): without it,
  serializing origin/destination for 12 containers fires 12 extra SELECTs
  (the classic N+1). One JOIN keeps it at one query.
- Telemetry history is an explicit bounded query, NOT the ORM
  relationship — the relationship would load the container's entire
  history, which grows forever. ?limit= defaults to 200, max 1000.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from .. import models
from ..db import get_db
from ..schemas import ContainerDetail, ContainerOut, PredictionOut

router = APIRouter(tags=["containers"])


@router.get("/containers", response_model=list[ContainerOut])
def list_containers(db: Session = Depends(get_db)):
    """All containers with current position/status — the map's data source."""
    return (
        db.query(models.Container)
        .options(joinedload(models.Container.route))
        .order_by(models.Container.id)
        .all()
    )


@router.get("/containers/{container_id}", response_model=ContainerDetail)
def get_container(
    container_id: int,
    limit: int = Query(default=200, ge=1, le=1000, description="max telemetry points"),
    db: Session = Depends(get_db),
):
    """Single container detail: snapshot, recent telemetry (newest first),
    and the latest prediction (null until the model pipeline has run)."""
    container = (
        db.query(models.Container)
        .options(joinedload(models.Container.route))
        .filter(models.Container.id == container_id)
        .first()
    )
    if container is None:
        raise HTTPException(status_code=404, detail=f"container {container_id} not found")

    telemetry = (
        db.query(models.TelemetryLog)
        .filter(models.TelemetryLog.container_id == container_id)
        .order_by(models.TelemetryLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    latest_prediction = (
        db.query(models.Prediction)
        .filter(models.Prediction.container_id == container_id)
        .order_by(models.Prediction.generated_at.desc())
        .first()
    )

    return ContainerDetail(
        id=container.id,
        name=container.name,
        current_lat=container.current_lat,
        current_lng=container.current_lng,
        status=container.status,
        route_id=container.route_id,
        last_updated=container.last_updated,
        origin_port=container.origin_port,
        destination_port=container.destination_port,
        telemetry=telemetry,
        latest_prediction=latest_prediction,
    )


@router.get("/containers/{container_id}/prediction", response_model=PredictionOut)
def get_latest_prediction(container_id: int, db: Session = Depends(get_db)):
    """Most recent prediction row for one container.

    404 with distinct messages for "container doesn't exist" vs "no
    prediction yet" so the frontend can tell a bug from an empty state.
    """
    container = db.get(models.Container, container_id)
    if container is None:
        raise HTTPException(status_code=404, detail=f"container {container_id} not found")

    prediction = (
        db.query(models.Prediction)
        .filter(models.Prediction.container_id == container_id)
        .order_by(models.Prediction.generated_at.desc())
        .first()
    )
    if prediction is None:
        raise HTTPException(
            status_code=404, detail=f"no prediction yet for container {container_id}"
        )
    return prediction
