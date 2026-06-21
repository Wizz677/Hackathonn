"""
Acceptance + unit tests for engine.py (build spec §10).

Run from backend/:  python -m pytest -q
The headline case is EXC-00145 (§4/§10.1) — it MUST pass.
"""

from datetime import date

from app import engine
from app.engine import acceptance_view, analyze_record

EVAL = date(2026, 4, 15)


# ---------------------------------------------------------------------------
# §10.1 — EXC-00145 acceptance case. MUST PASS.
# ---------------------------------------------------------------------------

EXC_00145 = {
    "exception_id": "EXC-00145",
    "type": "ADMIN_ACCESS",
    "requester": "USR-1234",
    "approver": "manager-001",
    "start_date": "2025-11-15",
    "end_date": "2025-12-15",
    "status": "ACTIVE",
    "renewal_count": 0,
}


def test_exc_00145_exact_output():
    """Match the spec §4 output precisely."""
    out = acceptance_view(EXC_00145, EVAL)
    assert out == {
        "exception_id": "EXC-00145",
        "risk_level": "CRITICAL",
        "alerts": [
            "EXPIRED_NOT_REVOKED: End date 2025-12-15 passed; still marked active",
            "OVERDUE_RENEWAL: Should have been renewed 4 months ago",
            "ELEVATED_PRIVILEGE: Admin access should be strictly temporary",
        ],
        "recommendation": "REVOKE IMMEDIATELY - was temporary, now 4 months overdue",
    }


def test_exc_00145_components():
    """Assert each acceptance requirement individually (spec §10.1)."""
    out = acceptance_view(EXC_00145, EVAL)
    assert out["risk_level"] == "CRITICAL"
    codes = [a.split(":")[0] for a in out["alerts"]]
    assert "EXPIRED_NOT_REVOKED" in codes
    assert "OVERDUE_RENEWAL" in codes
    assert "ELEVATED_PRIVILEGE" in codes
    assert out["recommendation"].startswith("REVOKE IMMEDIATELY")


# ---------------------------------------------------------------------------
# §10.2 — the brief's 3 sample rows parse and score sensibly.
# ---------------------------------------------------------------------------

SAMPLE_ROWS = [
    {
        "exception_id": "EXC-001",
        "type": "firewall_rule_open",
        "requester": "USR-2001",
        "approver": "manager-010",
        "justification": "Allow vendor SFTP egress to partner 10.4.2.0/24 for nightly batch",
        "start_date": "2026-03-01",
        "end_date": "2026-06-01",
        "status": "ACTIVE",
        "risk_level": "MEDIUM",
        "renewal_count": 1,
    },
    {
        "exception_id": "EXC-002",
        "type": "dev_environment",
        "requester": "USR-2002",
        "approver": "manager-011",
        "justification": "Sandbox cluster for ML model evaluation, isolated VPC, no prod data",
        "start_date": "2026-02-10",
        "end_date": "2026-05-10",
        "status": "PENDING",
        "risk_level": "LOW",
        "renewal_count": 0,
    },
    {
        "exception_id": "EXC-003",
        "type": "encryption_waiver",
        "requester": "USR-2003",
        "approver": "manager-012",
        "justification": "legacy",
        "start_date": "2024-01-05",
        "end_date": "2024-07-05",
        "status": "ACTIVE",
        "risk_level": "HIGH",
        "renewal_count": 0,
    },
]


def test_sample_rows_parse_and_score():
    for row in SAMPLE_ROWS:
        out = analyze_record(row, EVAL)
        assert out["exception_id"] == row["exception_id"]
        assert out["computed_risk_level"] in engine.RISK_ORDER


def test_exc_003_expired_long_duration():
    """EXC-003 encryption_waiver expired since 2024 -> high/critical with
    EXPIRED_NOT_REVOKED + LONG_DURATION (spec §10.2)."""
    out = analyze_record(SAMPLE_ROWS[2], EVAL)
    codes = [a.split(":")[0] for a in out["alerts"]]
    assert "EXPIRED_NOT_REVOKED" in codes
    assert "LONG_DURATION" in codes
    assert out["computed_risk_level"] in {"HIGH", "CRITICAL"}


def test_exc_002_stalled_review():
    """A PENDING request older than 30 days should flag STALLED_REVIEW."""
    out = analyze_record(SAMPLE_ROWS[1], EVAL)
    codes = [a.split(":")[0] for a in out["alerts"]]
    assert "STALLED_REVIEW" in codes


# ---------------------------------------------------------------------------
# Engine unit tests — individual rules.
# ---------------------------------------------------------------------------


def test_type_sensitivity_scale():
    assert engine.TYPE_SENSITIVITY["admin_access"] == "HIGH"
    assert engine.TYPE_SENSITIVITY["firewall_rule_open"] == "MEDIUM"
    assert engine.TYPE_SENSITIVITY["dev_environment"] == "LOW"


def test_sensitivity_takes_max_of_type_and_input():
    rec = engine.NormalizedRecord.from_raw(
        {"type": "dev_environment", "risk_level": "HIGH"}
    )
    assert engine.sensitivity(rec) == "HIGH"


def test_type_alone_does_not_force_high_risk():
    """A healthy high-sensitivity exception is one tier BELOW its sensitivity."""
    healthy_admin = {
        "exception_id": "EXC-HA",
        "type": "admin_access",
        "justification": "Scoped break-glass admin for INC-2210, reviewed weekly",
        "start_date": "2026-03-01",
        "end_date": "2026-07-01",
        "status": "ACTIVE",
        "renewal_count": 1,
    }
    out = analyze_record(healthy_admin, EVAL)
    assert out["computed_risk_level"] == "MEDIUM"  # not HIGH
    assert out["alerts"] == ["ELEVATED_PRIVILEGE: Admin access should be strictly temporary"]


def test_healthy_firewall_is_low():
    healthy_fw = {
        "exception_id": "EXC-HF",
        "type": "firewall_rule_open",
        "justification": "Open 8443 to monitoring collector for migration window CR-77",
        "start_date": "2026-03-10",
        "end_date": "2026-06-10",
        "status": "ACTIVE",
        "renewal_count": 1,
    }
    out = analyze_record(healthy_fw, EVAL)
    assert out["computed_risk_level"] in {"LOW", "MEDIUM"}
    assert out["alerts"] == []


def test_severe_anomaly_raises_high_sensitivity_to_high():
    """An expired-not-revoked firewall (medium sensitivity) lands HIGH."""
    row = {
        "exception_id": "EXC-EF",
        "type": "firewall_rule_open",
        "justification": "Vendor egress rule for partner batch transfer window",
        "start_date": "2026-01-20",  # < 180 days -> no LONG_DURATION
        "end_date": "2026-03-20",  # expired ~26 days
        "status": "ACTIVE",
        "renewal_count": 0,
    }
    out = analyze_record(row, EVAL)
    codes = {a.split(":")[0] for a in out["alerts"]}
    assert "EXPIRED_NOT_REVOKED" in codes and "LONG_DURATION" not in codes
    assert out["computed_risk_level"] == "HIGH"


def test_months_between():
    assert engine.months_between(date(2025, 12, 15), date(2026, 4, 15)) == 4
    assert engine.months_between(date(2025, 12, 16), date(2026, 4, 15)) == 3
    assert engine.months_between(date(2024, 7, 5), date(2026, 4, 15)) == 21


def test_no_renewal_suppressed_when_expired():
    """An expired record must NOT carry NO_RENEWAL_90_DAYS (OVERDUE covers it)."""
    out = analyze_record(EXC_00145, EVAL)
    codes = [a.split(":")[0] for a in out["alerts"]]
    assert "NO_RENEWAL_90_DAYS" not in codes


def test_no_renewal_fires_for_active_unrenewed():
    """A long-active, unexpired, unrenewed waiver flags NO_RENEWAL_90_DAYS."""
    row = {
        "exception_id": "EXC-NR",
        "type": "data_access",
        "justification": "Read access to anonymized analytics warehouse for Q2 reporting",
        "start_date": "2025-10-01",
        "end_date": "2026-10-01",
        "status": "ACTIVE",
        "renewal_count": 0,
    }
    out = analyze_record(row, EVAL)
    codes = [a.split(":")[0] for a in out["alerts"]]
    assert "NO_RENEWAL_90_DAYS" in codes
    assert "EXPIRED_NOT_REVOKED" not in codes


def test_vague_justification():
    assert engine._is_vague("")
    assert engine._is_vague("urgent")
    assert engine._is_vague("temporary fix")
    assert not engine._is_vague(
        "Allow vendor SFTP egress to partner for nightly batch transfer"
    )


def test_three_alerts_escalate_to_critical():
    """Three stacked alerts escalate even without elevated privilege."""
    row = {
        "exception_id": "EXC-STACK",
        "type": "encryption_waiver",
        "justification": "legacy",  # vague
        "start_date": "2024-01-01",
        "end_date": "2024-06-01",  # expired + long duration
        "status": "ACTIVE",
        "renewal_count": 0,
    }
    out = analyze_record(row, EVAL)
    assert out["computed_risk_level"] == "CRITICAL"
    assert len(out["alerts"]) >= 3


def test_healthy_record_no_action():
    row = {
        "exception_id": "EXC-OK",
        "type": "dev_environment",
        "justification": "Isolated CI runner sandbox for integration tests, no prod data access",
        "start_date": "2026-03-20",
        "end_date": "2026-07-20",
        "status": "ACTIVE",
        "renewal_count": 1,
    }
    out = analyze_record(row, EVAL)
    assert out["computed_risk_level"] == "LOW"
    assert out["alerts"] == []
    assert "Monitor" in out["recommendation"] or "No action" in out["recommendation"]


def test_tolerates_missing_fields():
    """Ingestion must never crash on imperfect input (spec §6)."""
    out = analyze_record({"exception_id": "EXC-EMPTY"}, EVAL)
    assert out["exception_id"] == "EXC-EMPTY"
    assert out["computed_risk_level"] in engine.RISK_ORDER


def test_framework_and_cia_tags_present():
    out = analyze_record(EXC_00145, EVAL)
    assert "NIST 800-53 AC-2" in out["framework_tags"]
    assert "Integrity" in out["cia_tags"]
