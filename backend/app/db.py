"""Database engine, session factory, and the get_db FastAPI dependency."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


def _normalize_database_url(url: str) -> str:
    """Pin the PostgreSQL driver explicitly.

    SQLAlchemy 2.1 changed the bare 'postgresql://' dialect to resolve to
    psycopg 3 — the first Render deploy failed with
    'ModuleNotFoundError: No module named psycopg' because only psycopg2
    was installed under the older default. Naming the dialect keeps
    behavior identical across SQLAlchemy versions and matches
    psycopg[binary] in requirements.txt. Hosted connection strings
    (Render, Supabase) start with bare 'postgresql://' and get normalized
    here; SQLite URLs pass through untouched.
    """
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


database_url = _normalize_database_url(settings.database_url)

# SQLite needs this flag to work with FastAPI's threaded request handling.
connect_args = {}
if database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

# pool_pre_ping=True: hosted Postgres poolers (and Render's load balancer)
# drop idle connections after a few minutes. Without pre-ping, the first
# request after an idle period dies with "connection already closed"; with
# it, SQLAlchemy tests each pooled connection and transparently replaces
# dead ones.
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)

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
