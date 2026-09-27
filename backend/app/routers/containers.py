"""Container read endpoints (spec section F).

- GET /containers                       — list all with current status + latest risk
- GET /containers/{id}                  — detail + bounded telemetry history
- GET /containers/{id}/prediction       — latest delay prediction

Query design notes:
- The list endpoint eager-loads routes with joinedload(): without it,
  serializing origin/destination for 12 containers fires 12 extra SELECTs
  (the classic N+1). One JOIN keeps it at one query.
- Latest predictions are denormalized onto the list payload (Phase 7: the
  map colors markers by risk) via one extra query: max(id) per container.
  Predictions are append-only, so max id = latest; the GROUP BY form is
  portable across SQLite and Postgres (DISTINCT ON is Postgres-only).
- Telemetry history is an explicit bounded query, NOT the ORM
  relationship — the relationship would load the container's entire
  history, which grows forever. ?limit= defaults to 200, max 1000.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from .. import models
from ..db import get_db
from ..schemas import ContainerDetail, ContainerOut, PredictionOut

router = APIRouter(tags=["containers"])


def _latest_predictions_by_container(db: Session) -> dict[int, models.Prediction]:
    """One query: the newest prediction row for every container that has one."""
    latest_ids = (
        db.query(func.max(models.Prediction.id).label("pid"))
        .group_by(models.Prediction.container_id)
        .subquery()
    )
    preds = (
        db.query(models.Prediction)
        .filter(models.Prediction.id.in_(db.query(latest_ids.c.pid)))
        .all()
    )
    return {p.container_id: p for p in preds}


@router.get("/containers", response_model=list[ContainerOut])
def list_containers(db: Session = Depends(get_db)):
    """All containers with current position/status/risk — the map's data source."""
    containers = (
        db.query(models.Container)
        .options(joinedload(models.Container.route))
        .order_by(models.Container.id)
        .all()
    )
    latest = _latest_predictions_by_container(db)

    return [
        ContainerOut(
            id=c.id,
            name=c.name,
            current_lat=c.current_lat,
            current_lng=c.current_lng,
            status=c.status,
            route_id=c.route_id,
            last_updated=c.last_updated,
            origin_port=c.origin_port,
            destination_port=c.destination_port,
            predicted_delay_hours=latest[c.id].predicted_delay_hours if c.id in latest else None,
            delay_probability=latest[c.id].delay_probability if c.id in latest else None,
        )
        for c in containers
    ]


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
        predicted_delay_hours=latest_prediction.predicted_delay_hours if latest_prediction else None,
        delay_probability=latest_prediction.delay_probability if latest_prediction else None,
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
