"""
models.py — SQLAlchemy ORM models (PostgreSQL-compatible schema).

We store the raw input contract columns plus the engine-computed fields, so the
analyzed view can be served and downloaded without recomputation. Computed JSON
fields (alerts, tags) use SQLAlchemy's JSON type, which maps to TEXT on SQLite
and JSONB-capable JSON on Postgres.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    # Wall-clock is used ONLY for DB row audit timestamps (created_at/updated_at),
    # never for risk or expiry math — that is always relative to EVALUATION_DATE
    # in engine.py. These columns record when a row was written, not "now" logic.
    return datetime.now(timezone.utc)


class ExceptionRecord(Base):
    """One GRC exception / policy waiver, with engine-computed enrichment."""

    __tablename__ = "exceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- input contract (spec §2) ---
    exception_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    requester: Mapped[str] = mapped_column(String(120))
    approver: Mapped[str] = mapped_column(String(120))
    justification: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    risk_level: Mapped[str] = mapped_column(String(16))  # input/declared risk
    renewal_count: Mapped[int] = mapped_column(Integer, default=0)

    # --- engine-computed fields (spec §2/§3) ---
    computed_risk_level: Mapped[str] = mapped_column(String(16), index=True)
    alerts: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    framework_tags: Mapped[list] = mapped_column(JSON, default=list)
    cia_tags: Mapped[list] = mapped_column(JSON, default=list)
    days_past_expiry: Mapped[int] = mapped_column(Integer, default=0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    def to_analyzed_dict(self) -> dict:
        """Serialize to the analyzed-record shape used by the API/frontend."""
        return {
            "exception_id": self.exception_id,
            "type": self.type,
            "requester": self.requester,
            "approver": self.approver,
            "justification": self.justification,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "status": self.status,
            "risk_level": self.risk_level,
            "renewal_count": self.renewal_count,
            "computed_risk_level": self.computed_risk_level,
            "alerts": self.alerts or [],
            "recommendation": self.recommendation,
            "framework_tags": self.framework_tags or [],
            "cia_tags": self.cia_tags or [],
            "days_past_expiry": self.days_past_expiry,
        }


class ActivityLog(Base):
    """Append-only lifecycle activity log (Renew / Revoke actions, spec §7.3)."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exception_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "exception_id": self.exception_id,
            "action": self.action,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
