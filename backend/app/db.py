"""
db.py — SQLAlchemy engine/session setup.

Uses SQLite for the demo but keeps a PostgreSQL-compatible schema and ORM usage,
so production can switch to Postgres by changing DATABASE_URL only (spec §1).
No engine logic lives here — this is pure plumbing.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Default to a local SQLite file next to the backend. Override with DATABASE_URL
# (e.g. postgresql+psycopg://user:pass@host/db) to run on Postgres unchanged.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./sunset.db")

# check_same_thread is a SQLite-only flag; omit it for other backends.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db():
    """FastAPI dependency yielding a session and always closing it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they do not exist."""
    # Import models so they register on Base.metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
