"""
report.py — portfolio / audit report builder (spec §5).

Pure: takes a list of analyzed record dicts (as produced by engine.analyze_record
or ExceptionRecord.to_analyzed_dict) plus the evaluation date, and returns the
plaintext report matching the brief's format, generated in milliseconds.
"""

from __future__ import annotations

from datetime import date, timedelta

from app import engine

# Pretty labels for the per-type breakdown.
TYPE_LABELS = {
    "admin_access": "Admin/Root Access",
    "firewall_rule_open": "Firewall Rules",
    "encryption_waiver": "Encryption Waivers",
    "data_access": "Data Access",
    "dev_environment": "Dev Environment",
}


def _risk_rank(record: dict) -> int:
    return engine.RISK_ORDER.get(record.get("computed_risk_level", "LOW"), 0)


def _has_alert(record: dict, code: str) -> bool:
    return any(a.startswith(code + ":") for a in record.get("alerts", []))


def _expiring_this_month(record: dict, eval_date: date) -> bool:
    end = engine.parse_date(record.get("end_date"))
    if end is None:
        return False
    return (
        end.year == eval_date.year
        and end.month == eval_date.month
        and end >= eval_date
    )


def build_report_data(records: list[dict], eval_date: date) -> dict:
    """Compute the structured numbers behind the report (also used by the API)."""
    active = [r for r in records if r.get("status") == "ACTIVE"]

    # Executive summary risk buckets (CRITICAL folded into HIGH for the 3-tier view).
    high = sum(1 for r in active if r["computed_risk_level"] in {"HIGH", "CRITICAL"})
    medium = sum(1 for r in active if r["computed_risk_level"] == "MEDIUM")
    low = sum(1 for r in active if r["computed_risk_level"] == "LOW")

    expiring = [r for r in active if _expiring_this_month(r, eval_date)]
    expiring_due = sum(
        1 for r in expiring if r["computed_risk_level"] in {"HIGH", "CRITICAL"}
    )
    expired_not_revoked = [r for r in records if _has_alert(r, "EXPIRED_NOT_REVOKED")]

    # Per-type breakdown over active records.
    by_type = {t: 0 for t in TYPE_LABELS}
    for r in active:
        if r["type"] in by_type:
            by_type[r["type"]] += 1
    other = by_type["data_access"] + by_type["dev_environment"]

    # Top high-risk exceptions: worst risk first, then most overdue.
    top = sorted(
        records,
        key=lambda r: (_risk_rank(r), r.get("days_past_expiry", 0)),
        reverse=True,
    )[:5]

    overdue_for_review = sum(1 for r in records if _has_alert(r, "OVERDUE_RENEWAL"))
    with_approver = sum(1 for r in records if (r.get("approver") or "").strip())
    pct_approved = round(100 * with_approver / len(records)) if records else 0

    return {
        "total_active": len(active),
        "high": high,
        "medium": medium,
        "low": low,
        "expiring_this_month": len(expiring),
        "expiring_due": expiring_due,
        "expired_not_revoked": len(expired_not_revoked),
        "by_type": by_type,
        "other": other,
        "top": top,
        "overdue_for_review": overdue_for_review,
        "pct_approved": pct_approved,
        "not_revoked_after_expiry": len(expired_not_revoked),
        "total": len(records),
    }


def build_report(records: list[dict], eval_date: date = engine.DEFAULT_EVALUATION_DATE) -> str:
    """Render the plaintext portfolio report (spec §5)."""
    d = build_report_data(records, eval_date)
    window_start = eval_date - timedelta(days=90)

    lines: list[str] = []
    lines.append("EXCEPTION PORTFOLIO SUMMARY")
    lines.append("============================")
    lines.append(f"Report Date: {eval_date.isoformat()}")
    lines.append(
        f"Time Range: Last 90 days ({window_start.isoformat()} to {eval_date.isoformat()})"
    )
    lines.append("")

    lines.append("EXECUTIVE SUMMARY")
    lines.append(f"Total Active Exceptions: {d['total_active']}")
    lines.append(f"  - HIGH Risk: {d['high']} (requires immediate attention)")
    lines.append(f"  - MEDIUM Risk: {d['medium']}")
    lines.append(f"  - LOW Risk: {d['low']}")
    lines.append(
        f"Expiring This Month: {d['expiring_this_month']} "
        f"({d['expiring_due']} due for renewal decision)"
    )
    lines.append(f"Expired (Not Revoked): {d['expired_not_revoked']} (should be closed)")
    lines.append("")

    lines.append("BREAKDOWN BY TYPE")
    lines.append(f"Admin/Root Access: {d['by_type']['admin_access']} (HIGH RISK)")
    lines.append(f"Firewall Rules: {d['by_type']['firewall_rule_open']} (MEDIUM RISK)")
    lines.append(f"Encryption Waivers: {d['by_type']['encryption_waiver']} (HIGH RISK)")
    lines.append(f"Other: {d['other']} (LOW/MEDIUM RISK)")
    lines.append("")

    lines.append("TOP HIGH-RISK EXCEPTIONS")
    for i, r in enumerate(d["top"], start=1):
        label = TYPE_LABELS.get(r["type"], r["type"])
        flag = _primary_flag(r)
        since = r.get("start_date") or "unknown"
        lines.append(
            f"{i}. {r.get('requester', '?')} {label} "
            f"[{r['computed_risk_level']}] (since {since}) - {flag}"
        )
    lines.append("")

    lines.append("RECOMMENDATIONS")
    for r in d["top"]:
        lines.append(f"-> {r.get('recommendation', 'Review')}")
    lines.append("")

    lines.append("NEXT AUDIT READINESS")
    lines.append("[x] All exceptions documented")
    lines.append(f"[x] {d['pct_approved']}% have approvals recorded")
    lines.append(f"[!] {d['overdue_for_review']} exceptions overdue for review")
    lines.append(
        f"[!] {d['not_revoked_after_expiry']} exceptions not revoked after expiry"
    )

    return "\n".join(lines)


def _primary_flag(record: dict) -> str:
    """The most salient alert code for a record, else its computed risk."""
    alerts = record.get("alerts", [])
    if alerts:
        return alerts[0].split(":")[0]
    return record.get("computed_risk_level", "OK")
