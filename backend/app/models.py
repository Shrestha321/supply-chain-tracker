"""SQLAlchemy ORM models — the four tables from the project spec (section E).

Design notes:
- sqlalchemy.JSON renders as JSONB on PostgreSQL (and plain JSON on SQLite,
  which keeps local smoke tests working).
- All timestamps are timezone-aware UTC (DateTime(timezone=True)). Shipping is
  inherently multi-timezone; storing UTC everywhere avoids a class of bugs.
- telemetry_log gets a composite index on (container_id, timestamp) because
  the hot query is "history for one container, newest first" (Phase 4).
- ON DELETE CASCADE on telemetry/predictions: deleting a container should not
  orphan its history rows.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin_port: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_port: Mapped[str] = mapped_column(String(100), nullable=False)
    # Ordered list of {"lat": float, "lng": float, "name": str} waypoints.
    waypoints: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    containers: Mapped[list["Container"]] = relationship(back_populates="route")

    def __repr__(self) -> str:
        return f"<Route {self.id} {self.origin_port} -> {self.destination_port}>"


class Container(Base):
    __tablename__ = "containers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    current_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    # e.g. "in_transit", "at_port", "delayed", "delivered"
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="in_transit")
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    route: Mapped["Route"] = relationship(back_populates="containers")
    telemetry: Mapped[list["TelemetryLog"]] = relationship(
        back_populates="container",
        cascade="all, delete-orphan",
        order_by="TelemetryLog.timestamp.desc()",
    )

    def __repr__(self) -> str:
        return f"<Container {self.id} {self.name} {self.status}>"


class TelemetryLog(Base):
    __tablename__ = "telemetry_log"
    __table_args__ = (
        Index("ix_telemetry_container_time", "container_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    container_id: Mapped[int] = mapped_column(
        ForeignKey("containers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    container: Mapped["Container"] = relationship(back_populates="telemetry")


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    container_id: Mapped[int] = mapped_column(
        ForeignKey("containers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    predicted_delay_hours: Mapped[float] = mapped_column(Float, nullable=False)
    # 0.0 - 1.0 probability that the container arrives late.
    delay_probability: Mapped[float] = mapped_column(Float, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    container: Mapped["Container"] = relationship()
