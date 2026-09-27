"""Database engine, session factory, and the get_db FastAPI dependency."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

# SQLite needs this flag to work with FastAPI's threaded request handling.
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

# pool_pre_ping=True: Supabase's pooler drops idle connections after a few
# minutes. Without pre-ping, the first request after an idle period dies with
# "connection already closed"; with it, SQLAlchemy tests each pooled
# connection and transparently replaces dead ones.
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


def get_db():
    """FastAPI dependency: one session per request, always closed after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
