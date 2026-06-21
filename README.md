# Sunset — GRC Exception & Policy Waiver Management

**Societe Generale PB-5 hackathon · Approach Option A: Smart Exception Lifecycle Automation**

Sunset is a 100% offline web app that gives a GRC team continuous visibility into
security exceptions and policy waivers — flagging the ones that have quietly
expired, over-stayed, or stalled, scoring their risk, and turning a manual
"1-hour audit" into a one-click report that generates in milliseconds.

---

## The problem

Security exceptions (admin access, firewall openings, encryption waivers, …) are
granted as *temporary* but rarely die on schedule. They expire and stay active,
run for years, or sit in review forever — and nobody notices until audit season.
The risk is invisible and the review is manual.

## Option A approach

A pure, deterministic **lifecycle engine** evaluates every exception against a
fixed **evaluation date** (never the system clock) and produces:

- a **computed risk level** on a `LOW < MEDIUM < HIGH < CRITICAL` scale,
- a set of explainable **alerts** (`CODE: explanation`),
- a single actionable **recommendation**,
- **compliance tags** (NIST 800-53, GDPR, CIS) and **CIA-triad** tags.

Everything else — dashboard, registry, detail, upload, portfolio report — is a
thin presentation layer over that engine.

---

## Architecture

```
/backend (Python + FastAPI + SQLAlchemy over SQLite, PG-compatible schema)
  app/engine.py    PURE risk/lifecycle logic — no I/O, no clock (the core, unit-tested)
  app/report.py    PURE §5 portfolio report builder
  app/seed.py      deterministic ~220-record synthetic dataset (+ sample CSV)
  app/models.py    SQLAlchemy models (exceptions + activity_log)
  app/schemas.py   Pydantic API shapes
  app/db.py        engine/session (swap to Postgres via DATABASE_URL only)
  app/main.py      FastAPI routes
  tests/           test_engine.py (incl. EXC-00145) + test_report.py
/frontend (React + Vite + Tailwind v4 + Recharts)
  src/views/       Dashboard, Registry, Detail, Upload, Report
/data/sample_exceptions.csv   100+ row sample matching the schema
```

**Why it stays offline & explainable:** the engine is a set of small pure
functions; reads recompute the analyzed view on the fly, so changing the
evaluation date in the UI genuinely shifts the whole portfolio. No external
APIs, no LLM calls, no threat feeds.

---

## How to run

**Backend** (Python 3.11+):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000        # seeds ~220 records on first boot
```

**Frontend** (Node 18+):

```bash
cd frontend
npm install
npm run dev                              # http://localhost:5173 (proxies /api -> :8000)
```

Open http://localhost:5173. To run on PostgreSQL instead of SQLite, set
`DATABASE_URL=postgresql+psycopg://user:pass@host/db` — no code changes.

---

## The acceptance test (spec §10)

```bash
cd backend && source .venv/bin/activate
python -m pytest -q
```

The headline case `test_exc_00145_exact_output` asserts the engine produces the
**exact** spec §4 output for `EXC-00145`:

```json
{
  "exception_id": "EXC-00145",
  "risk_level": "CRITICAL",
  "alerts": [
    "EXPIRED_NOT_REVOKED: End date 2025-12-15 passed; still marked active",
    "OVERDUE_RENEWAL: Should have been renewed 4 months ago",
    "ELEVATED_PRIVILEGE: Admin access should be strictly temporary"
  ],
  "recommendation": "REVOKE IMMEDIATELY - was temporary, now 4 months overdue"
}
```

`EXC-00145` is also seeded, so you can see the same output in the UI detail view.

### A note on alert semantics (the one judgment call)

`EXC-00145` is *expired*, so it raises `OVERDUE_RENEWAL` — and we deliberately
**suppress** `NO_RENEWAL_90_DAYS` once a record is past expiry (the overdue alert
is the more specific signal). `LONG_DURATION`, by contrast, *does* fire on
expired-but-active records (e.g. the brief's multi-year `EXC-003`). This
asymmetry is what makes both acceptance cases come out exactly right, and it is
pinned by `test_no_renewal_suppressed_when_expired` and
`test_exc_003_expired_long_duration`.

---

## Option A deliverables → where implemented

| Option A deliverable | Implementation |
| --- | --- |
| Full visibility into all exceptions | `Dashboard.jsx`, `Registry.jsx` + `GET /api/dashboard`, `/api/exceptions` |
| Expiry accuracy (expired-not-revoked detection) | `engine.compute_alerts` → `EXPIRED_NOT_REVOKED`, `OVERDUE_RENEWAL` |
| Risk scoring (4-tier + escalation) | `engine.base_risk`, `engine.escalate_risk` |
| Explainable alerts | `engine.compute_alerts` (7 rules, `CODE: explanation`) |
| Actionable recommendations | `engine.build_recommendation` |
| Compliance / CIA mapping | `engine.framework_tags`, `engine.cia_tags` |
| Lifecycle actions (Renew / Revoke + log) | `POST /api/exceptions/{id}/action`, `ActivityLog`, `Detail.jsx` |
| CSV ingestion (≥100 validation) | `POST /api/upload`, `Upload.jsx` |
| One-click portfolio / audit report | `report.py`, `GET /api/report`, `Report.jsx` |
| Analyzed-record export (JSON/CSV) | `GET /api/export.json`, `/api/export.csv` |
| Time-travel demo (configurable eval date) | `STATE.evaluation_date`, `POST /api/settings`, header date control |

## What we deliberately did **not** build (spec §8)

No CVE/KEV threat feeds, attack-path graphs, AI/LLM chatbot, exploit simulators,
blockchain gimmicks, real auth/SSO, email, multi-tenancy, or any external API.
Every feature traces to a requirement in §1–§7.
