"""
Tests for seed + report (build spec §10.2, §10.3, §10.5).

These cover the dataset generator and the portfolio report without needing a
running server or a database — the engine and report layers are pure.
"""

from datetime import date

from app import engine, report, seed

EVAL = date(2026, 4, 15)


def _analyzed_dataset():
    records = seed.generate_records()
    return records, [engine.analyze_record(r, EVAL) for r in records]


def test_seed_produces_100_plus_analyzed_rows():
    """§10.3 — 100+ rows produce analyzed output."""
    records, analyzed = _analyzed_dataset()
    assert len(records) >= 100
    assert all("computed_risk_level" in a and "alerts" in a for a in analyzed)


def test_seed_is_deterministic():
    a = seed.generate_records()
    b = seed.generate_records()
    assert a == b  # fixed RNG seed -> reproducible demo


def test_seed_includes_interesting_cases():
    """The deliberate problem cases must exist so the demo is populated (§6)."""
    _, analyzed = _analyzed_dataset()
    codes = {a.split(":")[0] for rec in analyzed for a in rec["alerts"]}
    assert {"EXPIRED_NOT_REVOKED", "LONG_DURATION", "STALLED_REVIEW",
            "VAGUE_JUSTIFICATION"} <= codes
    active = sum(1 for r in analyzed if r["status"] == "ACTIVE")
    assert 160 <= active <= 200  # aim ~180 active


def test_exc_00145_seeded_and_critical():
    _, analyzed = _analyzed_dataset()
    by_id = {a["exception_id"]: a for a in analyzed}
    assert "EXC-00145" in by_id
    assert by_id["EXC-00145"]["computed_risk_level"] == "CRITICAL"


def test_report_matches_section5_structure():
    """§10.5 — portfolio report generates with the §5 headings."""
    _, analyzed = _analyzed_dataset()
    text = report.build_report(analyzed, EVAL)
    for heading in (
        "EXCEPTION PORTFOLIO SUMMARY",
        "Report Date: 2026-04-15",
        "EXECUTIVE SUMMARY",
        "Total Active Exceptions:",
        "BREAKDOWN BY TYPE",
        "Admin/Root Access:",
        "TOP HIGH-RISK EXCEPTIONS",
        "RECOMMENDATIONS",
        "NEXT AUDIT READINESS",
    ):
        assert heading in text, f"missing heading: {heading}"


def test_report_data_counts_are_consistent():
    _, analyzed = _analyzed_dataset()
    d = report.build_report_data(analyzed, EVAL)
    assert d["total_active"] == sum(1 for r in analyzed if r["status"] == "ACTIVE")
    assert d["high"] + d["medium"] + d["low"] == d["total_active"]
