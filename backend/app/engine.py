"""
engine.py — PURE risk & lifecycle logic for the "Sunset" GRC Exception engine.

This module is the heart of the project and is the part the team defends in Q&A.
Design rules (enforced by code review and tests):

  * 100% PURE: no I/O, no DB, no network, no system clock. Every function is a
    deterministic transformation of its inputs. All time math is relative to a
    single configurable EVALUATION_DATE (default 2026-04-15, the brief's report
    date) — we NEVER call date.today().
  * Fully unit-tested: see backend/tests/test_engine.py, including the
    acceptance case EXC-00145 from the build spec §4/§10.

Pipeline for a single record (see `analyze_record`):
    normalize input -> compute base risk -> compute alerts ->
    escalate risk -> build recommendation -> attach framework/CIA tags.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

# The single source of "now". The brief's report is dated 2026-04-15, so all
# expiry / duration math is measured against this date. Callers may override it
# (the frontend Settings control does exactly that, to show the portfolio shift
# over time), but we never fall back to the wall clock.
DEFAULT_EVALUATION_DATE = date(2026, 4, 15)

# Ordinal risk scale: LOW < MEDIUM < HIGH < CRITICAL. We compare risks by their
# integer rank so "escalate" / "max" operations are unambiguous.
RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
RISK_BY_RANK = {v: k for k, v in RISK_ORDER.items()}

# Base inherent risk per exception type (spec §3a).
TYPE_BASE_RISK = {
    "admin_access": "HIGH",
    "encryption_waiver": "HIGH",
    "data_access": "HIGH",
    "firewall_rule_open": "MEDIUM",
    "dev_environment": "LOW",
}

# Canonical set of valid types (used for normalization / validation).
VALID_TYPES = set(TYPE_BASE_RISK)

# Valid lifecycle statuses (spec §2).
VALID_STATUSES = {"ACTIVE", "EXPIRED", "PENDING", "REVOKED", "RENEWED"}

# Generic / low-information justification phrases that should be flagged
# (spec §3b VAGUE_JUSTIFICATION). Matched case-insensitively as substrings.
VAGUE_PATTERNS = ("temporary", "legacy", "business need", "urgent")

# A justification shorter than this many characters is considered too thin.
MIN_JUSTIFICATION_LEN = 15

# Thresholds (days) used by the duration-based alerts.
LONG_DURATION_DAYS = 180
NO_RENEWAL_DAYS = 90
STALLED_REVIEW_DAYS = 30


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def parse_date(value: Any) -> date | None:
    """Parse a YYYY-MM-DD string (or pass through a date) -> date or None.

    Tolerant by design: ingestion must never crash on imperfect input
    (spec §6). Unparseable / empty values become None and are handled
    gracefully downstream.
    """
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def normalize_type(value: Any) -> str:
    """Normalize a type to canonical lower_snake_case (accepts upper/lower)."""
    if value is None:
        return ""
    return str(value).strip().lower()


def normalize_status(value: Any) -> str:
    """Normalize a status to upper case."""
    if value is None:
        return ""
    return str(value).strip().upper()


def normalize_risk(value: Any) -> str:
    """Normalize an input risk_level to upper case; default LOW if missing."""
    if value is None or str(value).strip() == "":
        return "LOW"
    norm = str(value).strip().upper()
    return norm if norm in RISK_ORDER else "LOW"


def max_risk(a: str, b: str) -> str:
    """Return the higher of two risk levels on the LOW<MED<HIGH<CRITICAL scale."""
    return a if RISK_ORDER.get(a, 0) >= RISK_ORDER.get(b, 0) else b


def days_between(earlier: date, later: date) -> int:
    """Signed day count later - earlier."""
    return (later - earlier).days


def months_between(earlier: date, later: date) -> int:
    """Whole calendar months from `earlier` to `later` (>=0 if later>=earlier).

    Used for the "{N} months overdue / old" phrasing. We count full months:
    e.g. 2025-12-15 -> 2026-04-15 is exactly 4 months. If the later day-of-month
    has not yet reached the earlier day-of-month, the final month is not counted.
    """
    months = (later.year - earlier.year) * 12 + (later.month - earlier.month)
    if later.day < earlier.day:
        months -= 1
    return max(months, 0)


# ---------------------------------------------------------------------------
# Normalized record
# ---------------------------------------------------------------------------


@dataclass
class NormalizedRecord:
    """A cleaned, type-safe view of a raw input record (CSV row or JSON dict)."""

    exception_id: str
    type: str
    requester: str
    approver: str
    justification: str
    start_date: date | None
    end_date: date | None
    status: str
    input_risk_level: str
    renewal_count: int = 0
    # Whether a justification was actually supplied in the input. A *missing*
    # field is not the same as an empty one: we only judge justification quality
    # (VAGUE_JUSTIFICATION) when the requester actually provided text. This is
    # why the acceptance case EXC-00145, which omits justification entirely,
    # carries exactly three alerts and not a fabricated vagueness flag.
    justification_provided: bool = True

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "NormalizedRecord":
        """Build a NormalizedRecord from a raw dict, tolerating missing fields."""

        def get(*keys: str, default: Any = "") -> Any:
            for k in keys:
                if k in raw and raw[k] is not None:
                    return raw[k]
            return default

        try:
            renewal = int(get("renewal_count", default=0) or 0)
        except (ValueError, TypeError):
            renewal = 0

        provided = raw.get("justification") not in (None, "")

        return cls(
            exception_id=str(get("exception_id")).strip(),
            type=normalize_type(get("type")),
            requester=str(get("requester")).strip(),
            approver=str(get("approver")).strip(),
            justification=str(get("justification")).strip(),
            start_date=parse_date(get("start_date", default=None)),
            end_date=parse_date(get("end_date", default=None)),
            status=normalize_status(get("status")),
            input_risk_level=normalize_risk(get("risk_level")),
            renewal_count=renewal,
            justification_provided=provided,
        )


# ---------------------------------------------------------------------------
# §3a — base risk
# ---------------------------------------------------------------------------


def base_risk(rec: NormalizedRecord) -> str:
    """Inherent risk = max(type base, declared input risk_level) — spec §3a."""
    type_base = TYPE_BASE_RISK.get(rec.type, "LOW")
    return max_risk(type_base, rec.input_risk_level)


def is_expired(rec: NormalizedRecord, eval_date: date) -> bool:
    """True if the waiver is past its expiry date (end_date < EVALUATION_DATE)."""
    return rec.end_date is not None and rec.end_date < eval_date


# ---------------------------------------------------------------------------
# §3b — alerts
# ---------------------------------------------------------------------------


def compute_alerts(rec: NormalizedRecord, eval_date: date) -> list[tuple[str, str]]:
    """Return ordered (code, explanation) alert tuples for a record (spec §3b).

    Order matters: it matches the acceptance output in spec §4
    (EXPIRED_NOT_REVOKED, OVERDUE_RENEWAL, ELEVATED_PRIVILEGE, ...).
    """
    alerts: list[tuple[str, str]] = []
    expired = is_expired(rec, eval_date)

    # EXPIRED_NOT_REVOKED — past expiry but still marked active.
    if expired and rec.status == "ACTIVE":
        alerts.append((
            "EXPIRED_NOT_REVOKED",
            f"End date {rec.end_date.isoformat()} passed; still marked active",
        ))

    # OVERDUE_RENEWAL — past end_date and not yet revoked/renewed.
    if expired and rec.status in {"ACTIVE", "EXPIRED", "PENDING"}:
        months = months_between(rec.end_date, eval_date)
        alerts.append((
            "OVERDUE_RENEWAL",
            f"Should have been renewed {months} months ago",
        ))

    # ELEVATED_PRIVILEGE — admin/root access must be strictly temporary.
    if rec.type == "admin_access":
        alerts.append((
            "ELEVATED_PRIVILEGE",
            "Admin access should be strictly temporary",
        ))

    # LONG_DURATION — an active waiver running longer than the temporary window.
    # Note: this fires even for expired-not-revoked records (status ACTIVE),
    # which is what surfaces multi-year waivers like the brief's EXC-003.
    if rec.status == "ACTIVE" and rec.start_date is not None:
        active_days = days_between(rec.start_date, eval_date)
        if active_days > LONG_DURATION_DAYS:
            alerts.append((
                "LONG_DURATION",
                f"Active {active_days} days; exceeds temporary duration",
            ))

    # NO_RENEWAL_90_DAYS — still within validity but unrenewed for 90+ days.
    # Deliberately suppressed once a record is past expiry: at that point the
    # OVERDUE_RENEWAL alert is the correct, more specific signal (this is why
    # EXC-00145, which is expired, does NOT also carry NO_RENEWAL_90_DAYS).
    if (
        rec.status == "ACTIVE"
        and not expired
        and rec.start_date is not None
        and days_between(rec.start_date, eval_date) > NO_RENEWAL_DAYS
        and rec.renewal_count == 0
    ):
        alerts.append(("NO_RENEWAL_90_DAYS", "No renewal in 90+ days"))

    # STALLED_REVIEW — a PENDING request that has sat too long.
    if rec.status == "PENDING" and rec.start_date is not None:
        pending_days = days_between(rec.start_date, eval_date)
        if pending_days > STALLED_REVIEW_DAYS:
            alerts.append((
                "STALLED_REVIEW",
                f"Pending review {pending_days} days",
            ))

    # VAGUE_JUSTIFICATION — empty, too short, or generic boilerplate. Only
    # evaluated when a justification was actually supplied (see field comment).
    if rec.justification_provided and _is_vague(rec.justification):
        alerts.append((
            "VAGUE_JUSTIFICATION",
            "Justification is vague or generic",
        ))

    return alerts


def _is_vague(justification: str) -> bool:
    """True if a justification is empty, too short, or matches generic patterns."""
    text = (justification or "").strip().lower()
    if len(text) < MIN_JUSTIFICATION_LEN:
        return True
    return any(pat in text for pat in VAGUE_PATTERNS)


# ---------------------------------------------------------------------------
# §3c — risk escalation
# ---------------------------------------------------------------------------


def escalate_risk(
    rec: NormalizedRecord,
    eval_date: date,
    alert_codes: set[str],
) -> str:
    """Compute the final computed_risk_level from base risk + alerts (spec §3c)."""
    computed = base_risk(rec)
    expired = is_expired(rec, eval_date)
    overdue_months = (
        months_between(rec.end_date, eval_date) if expired and rec.end_date else 0
    )

    # Escalate to CRITICAL when elevated privilege combines with an expiry/overdue
    # problem, OR when three or more alerts stack on one record.
    elevated = "ELEVATED_PRIVILEGE" in alert_codes
    expired_alert = "EXPIRED_NOT_REVOKED" in alert_codes
    if elevated and (expired_alert or overdue_months >= 3):
        return "CRITICAL"
    if len(alert_codes) >= 3:
        return "CRITICAL"

    # Otherwise an expired-not-revoked record is at least HIGH; else base risk.
    if expired_alert:
        return max_risk(computed, "HIGH")
    return computed


# ---------------------------------------------------------------------------
# §3d — recommendation
# ---------------------------------------------------------------------------


def build_recommendation(
    rec: NormalizedRecord,
    eval_date: date,
    computed_risk: str,
    alert_codes: set[str],
) -> str:
    """One actionable sentence for the record (spec §3d)."""
    expired = is_expired(rec, eval_date)
    overdue_months = (
        months_between(rec.end_date, eval_date) if expired and rec.end_date else 0
    )

    # CRITICAL and expired/overdue -> revoke now.
    if computed_risk == "CRITICAL" and (expired or overdue_months > 0):
        return (
            f"REVOKE IMMEDIATELY - was temporary, now {overdue_months} months overdue"
        )

    # Overdue but not critical -> ask for renewal justification.
    if expired:
        return (
            f"Request renewal justification - {overdue_months} months old, needs review"
        )

    # Long-running (still active) waiver -> accelerate remediation.
    if "LONG_DURATION" in alert_codes:
        return "Accelerate remediation - multi-year waiver is not sustainable"

    # Healthy. If it has a future expiry, surface the countdown.
    if rec.status == "ACTIVE" and rec.end_date is not None:
        days_left = days_between(eval_date, rec.end_date)
        if days_left >= 0:
            return f"Monitor - expires in {days_left} days"
    return "No action needed - within policy"


# ---------------------------------------------------------------------------
# §3e — framework + CIA tags
# ---------------------------------------------------------------------------

# Per-type compliance framework mapping (spec §3e).
FRAMEWORK_TAGS = {
    "admin_access": ["NIST 800-53 AC-2", "CIS Controls 1.1"],
    "data_access": ["NIST 800-53 AC-2", "GDPR Article 25"],
    "encryption_waiver": ["GDPR Article 25", "NIST 800-53 PL-4"],
    "firewall_rule_open": ["CIS Controls 1.1", "NIST 800-53 PL-4"],
    "dev_environment": ["NIST 800-53 PL-4"],
}

# Per-type CIA-triad mapping (spec §3e).
CIA_TAGS = {
    "admin_access": ["Integrity", "Confidentiality"],
    "data_access": ["Confidentiality", "Integrity"],
    "encryption_waiver": ["Confidentiality"],
    "firewall_rule_open": ["Availability", "Confidentiality"],
    "dev_environment": ["Integrity"],
}


def framework_tags(rec: NormalizedRecord) -> list[str]:
    return list(FRAMEWORK_TAGS.get(rec.type, ["NIST 800-53 PL-4"]))


def cia_tags(rec: NormalizedRecord) -> list[str]:
    return list(CIA_TAGS.get(rec.type, ["Integrity"]))


# ---------------------------------------------------------------------------
# Top-level analysis
# ---------------------------------------------------------------------------


def analyze_record(
    raw: dict[str, Any], eval_date: date = DEFAULT_EVALUATION_DATE
) -> dict[str, Any]:
    """Analyze one raw record and return the enriched dict (spec §3/§4).

    Output keys mirror the input contract plus the engine-computed fields:
    computed_risk_level, alerts (["CODE: explanation", ...]), recommendation,
    framework_tags, cia_tags, days_past_expiry.
    """
    rec = NormalizedRecord.from_raw(raw)

    alert_pairs = compute_alerts(rec, eval_date)
    alert_codes = {code for code, _ in alert_pairs}
    alerts = [f"{code}: {msg}" for code, msg in alert_pairs]

    computed_risk = escalate_risk(rec, eval_date, alert_codes)
    recommendation = build_recommendation(rec, eval_date, computed_risk, alert_codes)

    days_past_expiry = (
        days_between(rec.end_date, eval_date)
        if rec.end_date is not None and rec.end_date < eval_date
        else 0
    )

    return {
        "exception_id": rec.exception_id,
        "type": rec.type,
        "requester": rec.requester,
        "approver": rec.approver,
        "justification": rec.justification,
        "start_date": rec.start_date.isoformat() if rec.start_date else None,
        "end_date": rec.end_date.isoformat() if rec.end_date else None,
        "status": rec.status,
        "risk_level": rec.input_risk_level,
        "renewal_count": rec.renewal_count,
        # --- engine-computed fields ---
        "computed_risk_level": computed_risk,
        "alerts": alerts,
        "recommendation": recommendation,
        "framework_tags": framework_tags(rec),
        "cia_tags": cia_tags(rec),
        "days_past_expiry": days_past_expiry,
    }


def acceptance_view(
    raw: dict[str, Any], eval_date: date = DEFAULT_EVALUATION_DATE
) -> dict[str, Any]:
    """The compact §4 acceptance shape: id, risk_level, alerts, recommendation."""
    full = analyze_record(raw, eval_date)
    return {
        "exception_id": full["exception_id"],
        "risk_level": full["computed_risk_level"],
        "alerts": full["alerts"],
        "recommendation": full["recommendation"],
    }
