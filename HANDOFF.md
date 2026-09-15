# CohortOS — Non-Technical & Integrator Handoff (Portion 7)

**Date**: 2026-08-17  
**Package version**: 0.7.0  
**Status**: Production-ready domain layer for a single-centre offline-first coaching OS.

## What is ready

| Module | SPEC | Status |
|--------|------|--------|
| Core tenancy, RBAC, audit, config | §0, §7, §10 schema | Done |
| Unified sync engine + NotificationService | §6, §7 | Done |
| Admission + batch + roll encoding + migration | §1 | Done ([LOCKED] roll, [BULLET] duplicates & history) |
| Attendance / irregularity / anti-proxy | §2 | Done ([LOCKED] bio/manual, [BULLET] cross-batch) |
| Payment + locking | §3 | Done ([BULLET] lock immutability) |
| Exams / results (permanent history) | §4 | Done |
| Content / Vault + access rules + anti-leak | §5 | Done ([BULLET] AND/OR, owner_only default, desk blocked) |
| Composition root `CohortOSApp` | Phase 4 | Done |
| Install + migration runner + E2E suite | Phase 4 | Done |

**Test count**: 239 pytest green (full tree).

## What is deliberately not in this package

- **UI / Electron / React** — next layer; this package is the domain brain.
- **Module 8** Student/Parent accounts — hard-stop until join-code decision is final (SPEC already [LOCKED] but build paused per BUILD_PLAN).
- **Module 9** AI Solve / Teach — Portion 8.
- **Module 10** multi-tenant SaaS / founder admin — Portion 10.
- **Live biometric hardware driver** — `pyzk` integration is planned at the API/desktop boundary; domain already accepts punches via `ingest_punch` / `ingest_biometric_batch`.

## How a non-technical owner can verify

1. Install Python 3.10+ and run `pip install -r requirements.txt`.
2. Run `python -m pytest tests/ -q` — must report all passed.
3. Open a Python REPL and run the bootstrap snippet from `INSTALL.md`. Create a student, mark attendance, lock a payment — no internet required.

## How an engineer integrates

```python
from services.app import create_app
app = create_app(tenant_id="...", mode="offline-first")
# All services share one DataAccessLayer + AuditService + ConfigService
app.admission.admit_student(...)
app.attendance.mark_manual(...)
app.payment.mark_paid(...); app.payment.lock_payment(...)
app.exam.enter_result(...)
app.content.create_resource(...); app.content.evaluate_access(...)
```

- Tenant isolation is enforced by `TenantContext` on every read/write.
- Locked payments, anti-leak desk block, roll migration history, and offline-first core actions are non-negotiable ([BULLET]/[LOCKED]).

## Known design notes

- Storage is SQLite-backed (`DataAccessLayer`). Default `:memory:` for tests; pass `db_path="/path/to/cohortos.db"` for durable persistence across restarts. Migrations 003–012 applied on file open. Service signatures unchanged.
- Migrations 001–002 are PostgreSQL reference schemas for the future cloud path. 003–009 are SQLite and applied by `scripts/migrate.py`.
- Day keys are canonical lowercase (`sat`/`mon`/…). Admission normalizes input; attendance comparisons are case-safe.

## Files added / changed in Portion 7

- `services/app.py` — composition root + bootstrap
- `cohortos/__init__.py` — public package entry
- `models/__init__.py`, `services/__init__.py`
- `pyproject.toml`, `requirements.txt`
- `scripts/migrate.py`
- `tests/test_portion7_e2e.py` (8 tests)
- `INSTALL.md`, `HANDOFF.md`, `PORTION_7_PLAN.md`, `PORTION_7_SUMMARY.md`
- Hardening: day-key normalization in admission + attendance; migration 008 stub replace

## Next recommended work

1. UI shell (Electron + React) against `CohortOSApp`.
2. Portion 8 — AI Solve + Teach (with grounding pipeline).
3. Optional: SQLite-backed `DataAccessLayer` for long-running desktop processes.

## Production API environment (required)

The production entry point `create_api_app_or_raise()` refuses to start unless all three of these are set to durable values:

| Variable | Purpose | What breaks if skipped |
|----------|---------|------------------------|
| `COHORTOS_JWT_SECRET` | Signs access/refresh JWTs | Tokens cannot be issued or verified; API will not start |
| `COHORTOS_AUTH_DB` | SQLite file for session families / used refresh JTIs | Logged-in users lose sessions on process restart; refresh rotation state is forgotten (must be a filesystem path, not `:memory:`) |
| `COHORTOS_CLOUD_DB` | SQLite file for the cloud sync operation log | Device-to-device sync and “laptop dies” recovery have no durable source of truth (must be a filesystem path, not `:memory:`) |

`create_api_app()` still defaults to `:memory:` for tests. Only the production entry enforces durable paths.
