"""GET /routes — route reference data.

Beyond the spec's endpoint list, but needed twice: the simulator fetches
route geometry from here (so it stays HTTP-only), and the Phase 5 map uses
it to draw route polylines under the container markers.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..schemas import RouteOut

router = APIRouter(tags=["routes"])


@router.get("/routes", response_model=list[RouteOut])
def list_routes(db: Session = Depends(get_db)):
    return db.query(models.Route).order_by(models.Route.id).all()
