"""
schemas.py — Pydantic models for API request/response shapes.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AnalyzedRecord(BaseModel):
    """An exception record with engine-computed enrichment (spec §3/§4)."""

    exception_id: str
    type: str
    requester: str
    approver: str
    justification: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str
    risk_level: str
    renewal_count: int = 0
    computed_risk_level: str
    alerts: list[str] = []
    recommendation: str
    framework_tags: list[str] = []
    cia_tags: list[str] = []
    days_past_expiry: int = 0


class AcceptanceRecord(BaseModel):
    """The compact spec §4 acceptance shape."""

    exception_id: str
    risk_level: str
    alerts: list[str]
    recommendation: str


class SummaryCard(BaseModel):
    total_active: int
    high_risk: int
    medium_risk: int
    low_risk: int
    critical_risk: int
    expiring_this_month: int
    expired_not_revoked: int


class TypeBreakdown(BaseModel):
    admin_access: int
    firewall_rule_open: int
    encryption_waiver: int
    data_access: int
    dev_environment: int


class DashboardResponse(BaseModel):
    evaluation_date: str
    summary: SummaryCard
    by_type: TypeBreakdown
    risk_distribution: dict[str, int]
    top_high_risk: list[AnalyzedRecord]


class LifecycleAction(BaseModel):
    """Body for a Renew / Revoke action (spec §7.3)."""

    action: str  # "renew" | "revoke"


class ActivityEntry(BaseModel):
    id: int
    exception_id: str
    action: str
    detail: str
    created_at: Optional[str] = None


class UploadResult(BaseModel):
    received: int
    valid: bool
    mode: str  # "replace" | "add"
    message: str
    records: list[AnalyzedRecord] = []


class SettingsBody(BaseModel):
    evaluation_date: str
