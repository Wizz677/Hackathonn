"""
seed.py — synthetic dataset generator (spec §6).

Generates ~220 realistic, deterministic records spread across all types,
statuses and risk levels, deliberately including the "interesting" cases the
dashboard / alerts / report need to look meaningful:
  * expired-not-revoked (status ACTIVE, end_date in the past)
  * long-running multi-year waivers
  * stalled PENDING reviews
  * vague / generic justifications
Aims for ~180 active records. Also writes the set to /data/sample_exceptions.csv.

Deterministic (fixed RNG seed) so the demo is reproducible run to run.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from app import engine
from app.db import SessionLocal
from app.models import ExceptionRecord

# CSV lives in the repo's /data directory (two levels up from this file).
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CSV_PATH = DATA_DIR / "sample_exceptions.csv"

CSV_COLUMNS = [
    "exception_id",
    "type",
    "requester",
    "approver",
    "justification",
    "start_date",
    "end_date",
    "status",
    "risk_level",
    "renewal_count",
]

TYPES = [
    "admin_access",
    "firewall_rule_open",
    "encryption_waiver",
    "data_access",
    "dev_environment",
]

# Specific, defensible justifications keyed by type (the "good" pool).
GOOD_JUSTIFICATIONS = {
    "admin_access": [
        "Break-glass DB admin for incident INC-{n} remediation, scoped to prod-eu",
        "Short-lived root on build host to rotate expired signing keys, ticket OPS-{n}",
    ],
    "firewall_rule_open": [
        "Allow vendor SFTP egress to partner 10.4.{n}.0/24 for nightly batch",
        "Open 8443 to monitoring collector during migration window CR-{n}",
    ],
    "encryption_waiver": [
        "Defer TLS on internal metrics bus pending hardware refresh, risk-accepted",
        "At-rest encryption waiver for ageing reporting DB scheduled for {n} decom",
    ],
    "data_access": [
        "Read access to anonymized analytics warehouse for Q{n} revenue reporting",
        "Cross-team access to ticketing export for audit sampling, no PII columns",
    ],
    "dev_environment": [
        "Isolated CI runner sandbox for integration tests, no prod data access",
        "Sandbox cluster for ML model evaluation, isolated VPC, ticket DEV-{n}",
    ],
}

# Generic / low-information justifications (the engine should flag these).
VAGUE_JUSTIFICATIONS = [
    "temporary",
    "legacy",
    "business need",
    "urgent",
    "needed",
    "see email",
]

EVAL = engine.DEFAULT_EVALUATION_DATE  # 2026-04-15

# Overall type mix — skewed toward lower-sensitivity resources, mirroring a real
# portfolio (lots of dev sandboxes and firewall rules, fewer admin/crypto waivers).
TYPE_WEIGHTS = {
    "dev_environment": 30,
    "firewall_rule_open": 30,
    "data_access": 15,
    "admin_access": 15,
    "encryption_waiver": 10,
}
# Severe / overdue cases skew toward higher-sensitivity, exposed resources — a
# long-overdue admin key or open firewall is far more common (and interesting)
# than a stale dev sandbox. Dev is deliberately omitted here.
SEVERE_TYPE_WEIGHTS = {
    "firewall_rule_open": 32,
    "admin_access": 26,
    "data_access": 22,
    "encryption_waiver": 20,
}
# Minor hygiene issues skew toward firewall so a realistic slice of them surface
# as MEDIUM rather than everything low-sensitivity collapsing to LOW.
MINOR_TYPE_WEIGHTS = {
    "firewall_rule_open": 45,
    "dev_environment": 18,
    "data_access": 14,
    "admin_access": 13,
    "encryption_waiver": 10,
}

# How many records of each lifecycle "profile" to generate (besides the explicit
# EXC-00145). Tuned so that, among ~180 active exceptions, the risk mix is
# realistic: a large healthy LOW/MEDIUM base with a ~18% minority of anomalies
# producing the HIGH/CRITICAL tail. See the printed distribution in the README.
PROFILE_COUNTS = {
    "healthy": 144,             # active, within expiry, recently reviewed
    "active_vague": 5,          # active but generic justification (minor)
    "active_no_renewal": 4,     # active 90+ days, never renewed (minor)
    "active_long_running": 18,  # active multi-/many-month waiver (severe)
    "expired_not_revoked": 8,   # past expiry, still active (severe) -> top list
    "pending_ok": 8,            # in review, recent
    "pending_stalled": 7,       # in review > 30 days (severe)
    "revoked": 12,              # closed
    "renewed": 7,               # renewed, healthy
    "expired_status": 6,        # acknowledged-expired (past end, status EXPIRED)
}


def _iso(d: date) -> str:
    return d.isoformat()


def _pick_type(rng: random.Random, weights: dict[str, int]) -> str:
    types = list(weights)
    return rng.choices(types, weights=[weights[t] for t in types], k=1)[0]


def _input_risk(rng: random.Random, rec_type: str) -> str:
    """Declared input risk, kept <= type sensitivity so sensitivity stays
    type-driven (a real analyst could still mark something higher)."""
    if rec_type == "dev_environment":
        return rng.choice(["LOW", "LOW", "MEDIUM"])
    if rec_type == "firewall_rule_open":
        # A realistic minority of firewall openings are externally-facing and
        # analyst-flagged HIGH; those raise sensitivity, so a healthy one is
        # MEDIUM rather than LOW. The rest stay LOW/MEDIUM.
        return rng.choice(["LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH"])
    return rng.choice(["MEDIUM", "HIGH"])


def _good_just(rng: random.Random, rec_type: str) -> str:
    return rng.choice(GOOD_JUSTIFICATIONS[rec_type]).format(n=rng.randint(100, 9999))


def _rec(rec_type, status, start, end, renewal, justification, rng) -> dict:
    """Assemble a raw record dict (exception_id is assigned later)."""
    return {
        "type": rec_type,
        "requester": f"USR-{rng.randint(1000, 9999)}",
        "approver": f"manager-{rng.randint(1, 40):03d}",
        "justification": justification,
        "start_date": _iso(start),
        "end_date": _iso(end),
        "status": status,
        "risk_level": _input_risk(rng, rec_type),
        "renewal_count": renewal,
    }


def _make(profile: str, rng: random.Random) -> dict:
    """Build one raw record for the given lifecycle profile."""
    if profile == "healthy":
        t = _pick_type(rng, TYPE_WEIGHTS)
        start = EVAL - timedelta(days=rng.randint(10, 150))  # < 180 -> not long
        # Future expiry; the lower bound dips into the current month so a
        # realistic handful show up as "expiring this month" on the report.
        end = EVAL + timedelta(days=rng.randint(8, 300))
        return _rec(t, "ACTIVE", start, end, rng.randint(1, 3), _good_just(rng, t), rng)

    if profile == "active_vague":
        t = _pick_type(rng, MINOR_TYPE_WEIGHTS)
        start = EVAL - timedelta(days=rng.randint(10, 150))
        end = EVAL + timedelta(days=rng.randint(30, 220))
        return _rec(t, "ACTIVE", start, end, rng.randint(1, 2),
                    rng.choice(VAGUE_JUSTIFICATIONS), rng)

    if profile == "active_no_renewal":
        t = _pick_type(rng, MINOR_TYPE_WEIGHTS)
        start = EVAL - timedelta(days=rng.randint(95, 175))  # > 90, < 180
        end = EVAL + timedelta(days=rng.randint(30, 220))
        return _rec(t, "ACTIVE", start, end, 0, _good_just(rng, t), rng)

    if profile == "active_long_running":
        t = _pick_type(rng, SEVERE_TYPE_WEIGHTS)
        start = EVAL - timedelta(days=rng.randint(220, 1500))  # 7mo .. ~4yr
        end = EVAL + timedelta(days=rng.randint(20, 200))      # still in force
        return _rec(t, "ACTIVE", start, end, rng.randint(1, 2), _good_just(rng, t), rng)

    if profile == "expired_not_revoked":
        t = _pick_type(rng, SEVERE_TYPE_WEIGHTS)
        if rng.random() < 0.6:  # multi-year, badly overdue -> CRITICAL on the top list
            start = EVAL - timedelta(days=rng.randint(260, 1600))
            end = EVAL - timedelta(days=rng.randint(30, 250))
        else:  # recently expired -> HIGH (firewall) / CRITICAL (elevated)
            start = EVAL - timedelta(days=rng.randint(70, 165))
            end = EVAL - timedelta(days=rng.randint(10, 45))
        just = rng.choice(VAGUE_JUSTIFICATIONS) if rng.random() < 0.3 else _good_just(rng, t)
        return _rec(t, "ACTIVE", start, end, 0, just, rng)

    if profile == "pending_ok":
        t = _pick_type(rng, TYPE_WEIGHTS)
        start = EVAL - timedelta(days=rng.randint(2, 25))  # < 30 -> not stalled
        end = EVAL + timedelta(days=rng.randint(30, 180))
        return _rec(t, "PENDING", start, end, 0, _good_just(rng, t), rng)

    if profile == "pending_stalled":
        t = _pick_type(rng, TYPE_WEIGHTS)
        start = EVAL - timedelta(days=rng.randint(40, 150))  # > 30 -> stalled
        end = EVAL + timedelta(days=rng.randint(30, 180))
        return _rec(t, "PENDING", start, end, 0, _good_just(rng, t), rng)

    if profile == "revoked":
        t = _pick_type(rng, TYPE_WEIGHTS)
        start = EVAL - timedelta(days=rng.randint(60, 600))
        end = EVAL + timedelta(days=rng.randint(-120, 120))
        return _rec(t, "REVOKED", start, end, rng.randint(0, 2), _good_just(rng, t), rng)

    if profile == "renewed":
        t = _pick_type(rng, TYPE_WEIGHTS)
        start = EVAL - timedelta(days=rng.randint(120, 600))
        end = EVAL + timedelta(days=rng.randint(30, 300))
        return _rec(t, "RENEWED", start, end, rng.randint(1, 3), _good_just(rng, t), rng)

    # expired_status — acknowledged-expired (past end, status EXPIRED)
    t = _pick_type(rng, TYPE_WEIGHTS)
    start = EVAL - timedelta(days=rng.randint(120, 900))
    end = EVAL - timedelta(days=rng.randint(20, 200))
    return _rec(t, "EXPIRED", start, end, rng.randint(0, 1), _good_just(rng, t), rng)


def _exc_00145() -> dict:
    """The brief's headline case — seeded so the demo detail view shows §4 exactly."""
    return {
        "exception_id": "EXC-00145",
        "type": "admin_access",
        "requester": "USR-1234",
        "approver": "manager-001",
        "justification": "Prod admin to debug payment gateway latency, INC-4471",
        "start_date": "2025-11-15",
        "end_date": "2025-12-15",
        "status": "ACTIVE",
        "risk_level": "HIGH",
        "renewal_count": 0,
    }


def generate_records(n: int = 220, *, rng: random.Random | None = None) -> list[dict]:
    """Generate `n` raw exception dicts with a realistic risk distribution.

    Records are built per lifecycle profile (see PROFILE_COUNTS), shuffled, then
    given sequential ids. EXC-00145 is always present and the profile counts are
    tuned for ~180 active records with a realistic HIGH/CRITICAL tail.
    """
    rng = rng or random.Random(42)

    pool: list[dict] = []
    for profile, count in PROFILE_COUNTS.items():
        for _ in range(count):
            pool.append(_make(profile, rng))
    rng.shuffle(pool)

    records: list[dict] = [_exc_00145()]
    next_id = 2
    for rec in pool[: n - 1]:
        if next_id == 145:  # reserved for EXC-00145
            next_id += 1
        rec["exception_id"] = f"EXC-{next_id:05d}"
        next_id += 1
        records.append(rec)

    return records


def write_csv(records: list[dict], path: Path = CSV_PATH) -> None:
    """Write the raw records to /data/sample_exceptions.csv."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for rec in records:
            writer.writerow({col: rec.get(col, "") for col in CSV_COLUMNS})


def analyzed_orm(raw: dict, eval_date: date = EVAL) -> ExceptionRecord:
    """Run the engine over a raw dict and build a persistable ORM row."""
    a = engine.analyze_record(raw, eval_date)
    return ExceptionRecord(
        exception_id=a["exception_id"],
        type=a["type"],
        requester=a["requester"],
        approver=a["approver"],
        justification=a["justification"],
        start_date=a["start_date"],
        end_date=a["end_date"],
        status=a["status"],
        risk_level=a["risk_level"],
        renewal_count=a["renewal_count"],
        computed_risk_level=a["computed_risk_level"],
        alerts=a["alerts"],
        recommendation=a["recommendation"],
        framework_tags=a["framework_tags"],
        cia_tags=a["cia_tags"],
        days_past_expiry=a["days_past_expiry"],
    )


def seed_if_empty(eval_date: date = EVAL) -> int:
    """Seed the DB and write the sample CSV if the table is empty (spec §6).

    Returns the number of records seeded (0 if the DB was already populated).
    """
    records = generate_records()
    # Always (re)write the sample CSV so /data stays in sync with the engine.
    write_csv(records)

    db = SessionLocal()
    try:
        existing = db.query(ExceptionRecord).count()
        if existing > 0:
            return 0
        db.add_all(analyzed_orm(r, eval_date) for r in records)
        db.commit()
        return len(records)
    finally:
        db.close()


if __name__ == "__main__":  # manual: python -m app.seed
    recs = generate_records()
    write_csv(recs)
    active = sum(1 for r in recs if r["status"] == "ACTIVE")
    print(f"Generated {len(recs)} records ({active} active) -> {CSV_PATH}")
