"""
main.py — FastAPI app + routes (spec §1, §6, §7).

The engine is the single source of risk truth: every read recomputes the
analyzed view on the fly from the raw input columns against the *current*
EVALUATION_DATE, so the Settings control genuinely shifts the portfolio over
time (spec §7). Lifecycle actions mutate persisted status; everything else is
derived. No external network calls anywhere (spec §1/§10.4).
"""

from __future__ import annotations

import csv
import io
import json
import time
from datetime import date

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app import engine, exporters, report, seed
from app.db import get_db, init_db
from app.models import ActivityLog, ExceptionRecord
from app.schemas import LifecycleAction, SettingsBody

app = FastAPI(title="Sunset — GRC Exception & Policy Waiver Management")

# Permissive CORS so the Vite dev server (5173) can call the API locally.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Current evaluation date (the engine's "now"). Mutable via /api/settings so the
# demo can show the portfolio shift over time. Defaults to the brief's date.
STATE = {"evaluation_date": engine.DEFAULT_EVALUATION_DATE}


def eval_date() -> date:
    return STATE["evaluation_date"]


@app.on_event("startup")
def _startup() -> None:
    """Create tables and seed ~220 records if the DB is empty (spec §6)."""
    init_db()
    seed.seed_if_empty(eval_date())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INPUT_COLUMNS = [
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

# Columns a valid upload must declare (renewal_count is optional, spec §2).
REQUIRED_COLUMNS = [c for c in INPUT_COLUMNS if c != "renewal_count"]


def _orm_to_raw(row: ExceptionRecord) -> dict:
    """The raw input-contract dict for a stored row (drops computed fields)."""
    return {
        "exception_id": row.exception_id,
        "type": row.type,
        "requester": row.requester,
        "approver": row.approver,
        "justification": row.justification,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "status": row.status,
        "risk_level": row.risk_level,
        "renewal_count": row.renewal_count,
    }


def _analyzed(row: ExceptionRecord) -> dict:
    """Recompute the analyzed view for a row against the current eval date."""
    return engine.analyze_record(_orm_to_raw(row), eval_date())


def _all_analyzed(db: Session) -> list[dict]:
    return [_analyzed(r) for r in db.query(ExceptionRecord).all()]


# ---------------------------------------------------------------------------
# Health / settings
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "evaluation_date": eval_date().isoformat()}


@app.get("/api/settings")
def get_settings() -> dict:
    return {"evaluation_date": eval_date().isoformat()}


@app.post("/api/settings")
def set_settings(body: SettingsBody) -> dict:
    parsed = engine.parse_date(body.evaluation_date)
    if parsed is None:
        raise HTTPException(400, "evaluation_date must be YYYY-MM-DD")
    STATE["evaluation_date"] = parsed
    return {"evaluation_date": parsed.isoformat()}


# ---------------------------------------------------------------------------
# Dashboard (spec §7.1)
# ---------------------------------------------------------------------------


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict:
    records = _all_analyzed(db)
    ed = eval_date()
    rdata = report.build_report_data(records, ed)

    active = [r for r in records if r["status"] == "ACTIVE"]
    risk_dist = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for r in active:
        risk_dist[r["computed_risk_level"]] += 1

    by_type = {t: 0 for t in engine.VALID_TYPES}
    for r in active:
        if r["type"] in by_type:
            by_type[r["type"]] += 1

    top = sorted(
        records,
        key=lambda r: (
            engine.RISK_ORDER.get(r["computed_risk_level"], 0),
            r["days_past_expiry"],
        ),
        reverse=True,
    )[:5]

    return {
        "evaluation_date": ed.isoformat(),
        "summary": {
            "total_active": len(active),
            "critical_risk": risk_dist["CRITICAL"],
            "high_risk": risk_dist["HIGH"],
            "medium_risk": risk_dist["MEDIUM"],
            "low_risk": risk_dist["LOW"],
            "expiring_this_month": rdata["expiring_this_month"],
            "expired_not_revoked": rdata["expired_not_revoked"],
        },
        "by_type": by_type,
        "risk_distribution": risk_dist,
        "top_high_risk": top,
    }


# ---------------------------------------------------------------------------
# Registry / detail (spec §7.2, §7.3)
# ---------------------------------------------------------------------------


@app.get("/api/exceptions")
def list_exceptions(
    db: Session = Depends(get_db),
    type: str | None = Query(None),
    status: str | None = Query(None),
    computed_risk: str | None = Query(None),
    search: str | None = Query(None),
    sort: str = Query("risk"),
) -> dict:
    records = _all_analyzed(db)

    if type:
        records = [r for r in records if r["type"] == type.lower()]
    if status:
        records = [r for r in records if r["status"] == status.upper()]
    if computed_risk:
        records = [
            r for r in records if r["computed_risk_level"] == computed_risk.upper()
        ]
    if search:
        q = search.lower()
        records = [
            r
            for r in records
            if q in r["exception_id"].lower()
            or q in r["requester"].lower()
            or q in r["approver"].lower()
            or q in r["justification"].lower()
        ]

    if sort == "risk":
        records.sort(
            key=lambda r: (
                engine.RISK_ORDER.get(r["computed_risk_level"], 0),
                len(r["alerts"]),
            ),
            reverse=True,
        )
    elif sort == "expiry":
        records.sort(key=lambda r: r.get("end_date") or "9999-99-99")
    elif sort == "id":
        records.sort(key=lambda r: r["exception_id"])

    return {"count": len(records), "records": records}


@app.get("/api/exceptions/{exception_id}")
def get_exception(exception_id: str, db: Session = Depends(get_db)) -> dict:
    row = (
        db.query(ExceptionRecord)
        .filter(ExceptionRecord.exception_id == exception_id)
        .first()
    )
    if not row:
        raise HTTPException(404, f"{exception_id} not found")
    analyzed = _analyzed(row)
    activity = (
        db.query(ActivityLog)
        .filter(ActivityLog.exception_id == exception_id)
        .order_by(ActivityLog.created_at.desc())
        .all()
    )
    analyzed["activity"] = [a.to_dict() for a in activity]
    return analyzed


@app.post("/api/exceptions/{exception_id}/action")
def lifecycle_action(
    exception_id: str, body: LifecycleAction, db: Session = Depends(get_db)
) -> dict:
    row = (
        db.query(ExceptionRecord)
        .filter(ExceptionRecord.exception_id == exception_id)
        .first()
    )
    if not row:
        raise HTTPException(404, f"{exception_id} not found")

    action = body.action.lower()
    if action == "revoke":
        row.status = "REVOKED"
        detail = "Exception revoked"
    elif action == "renew":
        row.status = "RENEWED"
        row.renewal_count = (row.renewal_count or 0) + 1
        detail = f"Exception renewed (renewal_count={row.renewal_count})"
    else:
        raise HTTPException(400, "action must be 'renew' or 'revoke'")

    db.add(ActivityLog(exception_id=exception_id, action=action.upper(), detail=detail))
    db.commit()
    db.refresh(row)
    return _analyzed(row)


# ---------------------------------------------------------------------------
# Upload (spec §6, §7.4)
# ---------------------------------------------------------------------------


@app.post("/api/upload")
async def upload_csv(
    file: UploadFile = File(...),
    mode: str = Query("add"),
    db: Session = Depends(get_db),
) -> dict:
    raw_bytes = await file.read()
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [(f or "").strip() for f in (reader.fieldnames or [])]
    rows = [dict(r) for r in reader]

    # Lightweight validation only — reject genuinely bad input, not small files.
    # The engine analyzes whatever number of valid records is uploaded.
    if not rows:
        raise HTTPException(400, "CSV is empty — no records to analyze.")
    missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
    if missing:
        raise HTTPException(
            400,
            "CSV is missing required column(s): " + ", ".join(missing),
        )

    if mode == "replace":
        db.query(ExceptionRecord).delete()
        db.query(ActivityLog).delete()

    analyzed_records = []
    seen = {
        r.exception_id
        for r in db.query(ExceptionRecord.exception_id).all()  # type: ignore
    } if mode != "replace" else set()

    for raw in rows:
        # Tolerate imperfect input; skip rows with no id rather than crashing.
        if not (raw.get("exception_id") or "").strip():
            continue
        if raw["exception_id"] in seen:
            continue
        seen.add(raw["exception_id"])
        orm = seed.analyzed_orm(raw, eval_date())
        db.add(orm)
        analyzed_records.append(engine.analyze_record(raw, eval_date()))

    db.commit()
    return {
        "received": len(rows),
        "valid": True,
        "mode": mode,
        "message": f"Persisted {len(analyzed_records)} records ({mode}).",
        "records": analyzed_records[:200],
    }


# ---------------------------------------------------------------------------
# Report (spec §5, §7.5) + exports (spec §4)
# ---------------------------------------------------------------------------


@app.get("/api/report")
def get_report(db: Session = Depends(get_db)) -> dict:
    t0 = time.perf_counter()
    records = _all_analyzed(db)
    ed = eval_date()
    text = report.build_report(records, ed)
    data = report.build_report_data(records, ed)
    seconds = round(time.perf_counter() - t0, 3)
    return {"report": text, "data": data, "generated_seconds": seconds}


@app.get("/api/report/download")
def download_report(db: Session = Depends(get_db)) -> PlainTextResponse:
    """Plain-text portfolio report (.txt) — the literal §5 format."""
    records = _all_analyzed(db)
    text = report.build_report(records, eval_date())
    return PlainTextResponse(
        text,
        headers={"Content-Disposition": "attachment; filename=portfolio_report.txt"},
    )


@app.get("/api/report.pdf")
def download_report_pdf(db: Session = Depends(get_db)) -> Response:
    """Clean, management-ready PDF rendering of the portfolio report."""
    records = _all_analyzed(db)
    pdf = exporters.report_pdf_bytes(records, eval_date())
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=portfolio_report.pdf"
        },
    )


@app.get("/api/report.xlsx")
def download_report_xlsx(db: Session = Depends(get_db)) -> Response:
    """Excel workbook: analyzed records sheet + a summary sheet."""
    records = _all_analyzed(db)
    xlsx = exporters.analyzed_xlsx_bytes(records, eval_date())
    return Response(
        xlsx,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": "attachment; filename=exception_portfolio.xlsx"
        },
    )


@app.get("/api/export.json")
def export_json(db: Session = Depends(get_db)) -> Response:
    records = _all_analyzed(db)
    payload = json.dumps(records, indent=2)
    return Response(
        payload,
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=analyzed_exceptions.json"
        },
    )


@app.get("/api/export.csv")
def export_csv(db: Session = Depends(get_db)) -> Response:
    records = _all_analyzed(db)
    buf = io.StringIO()
    cols = INPUT_COLUMNS + [
        "computed_risk_level",
        "alerts",
        "recommendation",
        "framework_tags",
        "cia_tags",
        "days_past_expiry",
    ]
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    for r in records:
        row = {c: r.get(c, "") for c in cols}
        # Flatten list columns for CSV.
        for k in ("alerts", "framework_tags", "cia_tags"):
            row[k] = " | ".join(r.get(k, []))
        writer.writerow(row)
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=analyzed_exceptions.csv"},
    )
