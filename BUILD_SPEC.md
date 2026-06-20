# CLAUDE CODE BUILD PROMPT — GRC Exception & Policy Waiver Management ("Sunset")

You are building a complete, demo-ready web application for the Societe Generale PB-5 hackathon (Approach **Option A: Smart Exception Lifecycle Automation**). Build it end to end in this repository, commit as you go, and verify it against the acceptance test in §10 before finishing.

**Guiding principles (read first):**
- **Match the expected output exactly** (§4). That is the primary success criterion.
- **Lean, not bloated.** Build only what's specified below. Quality and correctness over feature count. Every feature must trace to a requirement.
- **Explainable.** Clean, commented code a two-person team can defend line-by-line in a live Q&A.
- **100% offline.** No external network calls at runtime. The engine is pure local logic.

---

## 1. STACK & STRUCTURE

- **Backend:** Python + FastAPI. SQLAlchemy ORM over **SQLite** with a **PostgreSQL-compatible schema** (so production can switch to Postgres via connection string only). Pydantic for models. The risk/lifecycle engine lives in a pure, unit-tested module (`engine.py`) with no I/O.
- **Frontend:** React + Vite + Tailwind. Recharts for charts. Clean dark "security console" aesthetic, one accent color, fully responsive (must look right at ~390px for a mobile demo video).
- **No external runtime dependencies.** No third-party APIs, no cloud DB, no LLM calls.

```
/backend
  /app
    main.py            # FastAPI app + routes
    engine.py          # PURE risk/lifecycle logic (unit-tested)
    models.py          # SQLAlchemy models
    schemas.py         # Pydantic schemas
    seed.py            # synthetic dataset generator
    report.py          # portfolio report builder
    db.py              # SQLAlchemy engine/session (SQLite, PG-compatible)
  /tests
    test_engine.py     # acceptance tests incl. EXC-00145
  requirements.txt
/frontend
  ... React + Vite + Tailwind app
/data
  sample_exceptions.csv  # a 100+ row sample matching the schema
README.md
```

---

## 2. DATA SCHEMA (exact — do not add columns to the input contract)

Input CSV / record columns:
`exception_id, type, requester, approver, justification, start_date, end_date, status, risk_level`

- `type`: `admin_access`, `firewall_rule_open`, `encryption_waiver`, `data_access`, `dev_environment` (accept upper/lower case, normalize internally).
- `start_date`, `end_date`: `YYYY-MM-DD`. **`end_date` is the expiry date.**
- `status`: `ACTIVE`, `EXPIRED`, `PENDING`, `REVOKED`, `RENEWED`.
- `risk_level` (input): `HIGH` / `MEDIUM` / `LOW`.
- Also accept optional `renewal_count` (int, default 0) in JSON record inputs.

Stored/computed per record (added by the engine, not part of the input contract): `computed_risk_level`, `alerts` (JSON array), `recommendation`, `framework_tags`, `cia_tags`, `days_past_expiry`.

---

## 3. THE ENGINE (`engine.py`) — pure functions, fully unit-tested

All time math is relative to a single configurable **`EVALUATION_DATE`, default `2026-04-15`** (the brief's report date). Never use the system clock.

### 3a. Base risk by type → ordinal scale LOW < MEDIUM < HIGH < CRITICAL
- `admin_access`, `encryption_waiver`, `data_access` → HIGH
- `firewall_rule_open` → MEDIUM
- `dev_environment` → LOW
Base = max(type_base, input `risk_level`).

### 3b. Alerts — compute each, output as `"CODE: explanation"`
- `EXPIRED_NOT_REVOKED` — `end_date < EVALUATION_DATE` and status ACTIVE → "End date {end_date} passed; still marked active".
- `OVERDUE_RENEWAL` — past `end_date` → "Should have been renewed {N} months ago".
- `ELEVATED_PRIVILEGE` — type is admin/root → "Admin access should be strictly temporary".
- `LONG_DURATION` — active and `(EVALUATION_DATE − start_date) > 180 days` → "Active {N} days; exceeds temporary duration".
- `NO_RENEWAL_90_DAYS` — active > 90 days with renewal_count 0 → "No renewal in 90+ days".
- `STALLED_REVIEW` — status PENDING and `(EVALUATION_DATE − start_date) > 30 days` → "Pending review {N} days".
- `VAGUE_JUSTIFICATION` — justification empty/very short or matches generic patterns ("temporary", "legacy", "business need", "urgent") → "Justification is vague or generic".

### 3c. Risk escalation
- Escalate computed_risk_level to **CRITICAL** when `ELEVATED_PRIVILEGE` is present AND (`EXPIRED_NOT_REVOKED` OR overdue > ~90 days), OR when ≥3 alerts stack.
- Else computed_risk_level = base (but any EXPIRED_NOT_REVOKED keeps it at least HIGH).

### 3d. Recommendation (one actionable sentence)
- CRITICAL + expired/overdue → "REVOKE IMMEDIATELY - was temporary, now {N} months overdue".
- Overdue but not critical → "Request renewal justification - {N} months old, needs review".
- Long-running waiver → "Accelerate remediation - multi-year waiver is not sustainable".
- Healthy → "No action needed - within policy" / "Monitor - expires in {N} days".

### 3e. Framework + CIA tags
- Map each record to: NIST 800-53 **AC-2** (account mgmt) / **PL-4** (rules of behavior), **GDPR Article 25**, **CIS Controls 1.1** — choose the relevant ones per type.
- CIA tags: encryption_waiver→Confidentiality; data_access→Confidentiality/Integrity; admin_access→Integrity/Confidentiality; firewall→Availability/Confidentiality. (Reasonable mapping; keep simple.)

---

## 4. EXACT PER-RECORD OUTPUT (acceptance-critical — match precisely)

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
Expose this (a) in the record detail view, (b) as a downloadable JSON/CSV of analyzed records.

---

## 5. PORTFOLIO / AUDIT REPORT (`report.py`) — match the brief's format

One-click generate (and download) a report:
```
EXCEPTION PORTFOLIO SUMMARY
============================
Report Date: 2026-04-15
Time Range: <last 90 days>

EXECUTIVE SUMMARY
Total Active Exceptions: <n>
  - HIGH Risk: <n> (requires immediate attention)
  - MEDIUM Risk: <n>
  - LOW Risk: <n>
Expiring This Month: <n> (<n> due for renewal decision)
Expired (Not Revoked): <n> (should be closed)

BREAKDOWN BY TYPE
Admin/Root Access: <n> (HIGH RISK)
Firewall Rules: <n> (MEDIUM RISK)
Encryption Waivers: <n> (HIGH RISK)
Other: <n> (LOW/MEDIUM RISK)

TOP HIGH-RISK EXCEPTIONS
1. <requester> <type> ... (since <date>) — <flag>
...

RECOMMENDATIONS
→ <action per top risk>
...

NEXT AUDIT READINESS
 All exceptions documented
 <pct>% have approvals recorded
 <n> exceptions overdue for review
 <n> exceptions not revoked after expiry
```
Must generate in seconds (satisfies the "1-hour report" success criterion).

---

## 6. DATA INGESTION

- **Seed on startup if DB empty:** generate ~220 realistic records via `seed.py`, distributed across all types/statuses/risk levels, deliberately including expired-not-revoked, long-running (multi-year), stalled-review, and vague-justification cases so the dashboard, alerts, and report are populated and interesting (aim for ~180 active). Also write this set to `/data/sample_exceptions.csv`.
- **CSV upload:** accept a `.csv` in the schema, validate **≥100 records**, parse, persist, analyze, and show the per-record output table + downloadable analyzed output. Offer "replace" vs "add". Tolerate missing optional fields; never crash on imperfect input.

---

## 7. FRONTEND (these views only — no others)

1. **Dashboard:** summary cards (total active, HIGH/MED/LOW counts, expiring this month, expired-not-revoked); breakdown by type; a small risk-distribution chart; "top high-risk exceptions" list.
2. **Registry:** sortable/filterable/searchable table of all exceptions (filter by type, status, computed risk); color-coded status; computed risk + alert-count badges; row → detail.
3. **Detail:** full record + computed risk_level + alerts + recommendation + framework/CIA tags + a tooltip explaining how the risk was computed. **Lifecycle actions: Renew / Revoke** (update status, append to activity log).
4. **Upload:** CSV upload with ≥100 validation + analyzed results.
5. **Report:** generate, view, and download the portfolio report (§5).
- Include a small **Settings** control to change `EVALUATION_DATE` (so the demo can show the portfolio shift over time) and an **"Approach: Option A"** label + a success-criteria strip (Visibility 100%, Expiry accuracy, Risk scoring, Audit readiness "<X>s").

---

## 8. DO NOT BUILD (avoid overkill)

❌ NVD/CVE/KEV threat feeds or "actively exploited" logic · ❌ attack-path graphs · ❌ AI/LLM chatbot or copilot · ❌ exploit simulators · ❌ blockchain/hash-ledger gimmicks · ❌ real auth/SSO · ❌ real email · ❌ multi-tenancy · ❌ any external API. Anything not in §1–§7 is out of scope.

---

## 9. CODE QUALITY & GIT

- Keep `engine.py` pure and thoroughly commented; it's the part you'll defend in Q&A.
- Commit in small, meaningful increments with clear messages (the commit history is the team's thought-process evidence).
- Write a strong **README.md**: problem, Option A approach, architecture, how to run, the acceptance test, and a mapping of each Option A deliverable → where it's implemented.

---

## 10. ACCEPTANCE TESTS (write these in `test_engine.py` and run them)

1. **EXC-00145 case:** input `{exception_id:"EXC-00145", type:"ADMIN_ACCESS", requester:"USR-1234", approver:"manager-001", start_date:"2025-11-15", end_date:"2025-12-15", status:"ACTIVE", renewal_count:0}` with EVALUATION_DATE=2026-04-15 → output `risk_level:"CRITICAL"`, alerts containing EXPIRED_NOT_REVOKED, OVERDUE_RENEWAL, ELEVATED_PRIVILEGE, and a REVOKE recommendation. **Must pass.**
2. The brief's 3 sample rows (EXC-001/002/003) parse against the schema and score sensibly (EXC-003 encryption_waiver expired since 2024 → high/critical with EXPIRED_NOT_REVOKED + LONG_DURATION).
3. CSV upload of 100+ rows produces analyzed output.
4. App boots and runs with **no network** (verify no external calls).
5. Portfolio report generates and matches the §5 structure.

Run the test suite, confirm all pass, then report a short [DONE] checklist of §1–§7 with file references.

**Build it now, end to end. Start by scaffolding the repo and the engine + its tests, get EXC-00145 passing, then build outward to the API, seed data, frontend, and report.**
