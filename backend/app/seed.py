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
        "Temporary root on build host to rotate expired signing keys, ticket OPS-{n}",
    ],
    "firewall_rule_open": [
        "Allow vendor SFTP egress to partner 10.4.{n}.0/24 for nightly batch",
        "Open 8443 to monitoring collector during migration window CR-{n}",
    ],
    "encryption_waiver": [
        "Defer TLS on internal metrics bus pending hardware refresh, risk-accepted",
        "At-rest encryption waiver for legacy reporting DB scheduled for {n} decom",
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

STATUSES = ["ACTIVE", "EXPIRED", "PENDING", "REVOKED", "RENEWED"]
RISK_LEVELS = ["LOW", "MEDIUM", "HIGH"]

EVAL = engine.DEFAULT_EVALUATION_DATE  # 2026-04-15


def _iso(d: date) -> str:
    return d.isoformat()


def generate_records(n: int = 220, *, rng: random.Random | None = None) -> list[dict]:
    """Generate `n` raw exception dicts with a realistic, lopsided distribution."""
    rng = rng or random.Random(42)
    records: list[dict] = []

    # The brief's headline case — seeded so the demo detail view shows §4 exactly.
    records.append(
        {
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
    )

    # Range extended by one and skipping 145, since EXC-00145 is added above —
    # this keeps the total at exactly `n` with unique ids.
    for i in range(2, n + 2):
        if i == 145:
            continue
        exc_id = f"EXC-{i:05d}"
        rec_type = rng.choices(
            TYPES, weights=[22, 28, 14, 20, 16], k=1  # admin & firewall most common
        )[0]

        # ~82% active so we land near ~180 active out of 220 (spec §6).
        status = rng.choices(
            STATUSES, weights=[82, 6, 6, 3, 3], k=1
        )[0]

        # Pick a lifecycle "shape" to guarantee interesting cases exist.
        shape = rng.choices(
            ["healthy", "expired_not_revoked", "long_running", "stalled", "vague"],
            weights=[40, 22, 16, 10, 12],
            k=1,
        )[0]

        renewal_count = rng.choice([0, 0, 0, 1, 2])
        risk_level = rng.choice(RISK_LEVELS)
        justification = rng.choice(GOOD_JUSTIFICATIONS[rec_type]).format(
            n=rng.randint(100, 9999)
        )

        if shape == "healthy":
            # Keep the rolled status (most are ACTIVE, some EXPIRED/REVOKED/RENEWED),
            # giving realistic variety and landing active near ~180 of 220.
            start = EVAL - timedelta(days=rng.randint(10, 120))
            end = EVAL + timedelta(days=rng.randint(30, 200))
        elif shape == "expired_not_revoked":
            # Expired weeks-to-months ago but still marked ACTIVE.
            start = EVAL - timedelta(days=rng.randint(200, 520))
            end = EVAL - timedelta(days=rng.randint(20, 200))
            status = "ACTIVE"
        elif shape == "long_running":
            # Multi-year waiver, still active.
            start = EVAL - timedelta(days=rng.randint(500, 1500))
            end = EVAL + timedelta(days=rng.randint(15, 120))
            status = "ACTIVE"
        elif shape == "stalled":
            # Pending review that has sat well past 30 days.
            start = EVAL - timedelta(days=rng.randint(45, 180))
            end = EVAL + timedelta(days=rng.randint(30, 120))
            status = "PENDING"
        else:  # vague (keep rolled status for variety)
            start = EVAL - timedelta(days=rng.randint(30, 300))
            end = EVAL + timedelta(days=rng.randint(-60, 120))
            justification = rng.choice(VAGUE_JUSTIFICATIONS)

        records.append(
            {
                "exception_id": exc_id,
                "type": rec_type,
                "requester": f"USR-{rng.randint(1000, 9999)}",
                "approver": f"manager-{rng.randint(1, 40):03d}",
                "justification": justification,
                "start_date": _iso(start),
                "end_date": _iso(end),
                "status": status,
                "risk_level": risk_level,
                "renewal_count": renewal_count,
            }
        )

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
