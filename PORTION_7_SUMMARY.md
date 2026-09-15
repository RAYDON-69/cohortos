# Portion 7 — Compile + Non-Technical Handoff — DONE

**Completed**: 2026-08-17  
**Status**: Production-ready

## Deliverables

- `services/app.py` — `CohortOSApp` / `create_app()` composition root; shared DataAccessLayer; `bootstrap_centre()`
- `cohortos/` package entry (`from cohortos import create_app`)
- `pyproject.toml` + `requirements.txt` — installable as `cohortos` 0.7.0
- `scripts/migrate.py` — idempotent SQLite migration runner (003–009)
- `tests/test_portion7_e2e.py` — 8 multi-module E2E tests (happy path, anti-leak, roll migration, offline, irregularity, shared layer)
- `INSTALL.md`, `HANDOFF.md`
- Hardening:
  - Canonical lowercase day keys on batch create + case-safe attendance comparison (fixes Mon vs mon mismatch)
  - Migration 008 replaces 005 stub `exam_results` so indexes succeed

## Tests

- Full tree: **239/239** pytest green
- Portion 7 E2E: **8/8**

## SPEC coverage (compile milestone)

| Item | Status |
|------|--------|
| Single composition root for Modules 1–5 + sync/notification | ✅ |
| Offline-first core actions with zero network | ✅ |
| [BULLET] history preserved on roll/batch migration | ✅ (E2E) |
| [BULLET] payment lock immutability | ✅ (E2E) |
| [BULLET][LOCKED] anti-leak desk blocked | ✅ (E2E) |
| Access rules AND composition | ✅ (E2E) |
| Install + non-technical handoff docs | ✅ |
| Integratable into Electron / FastAPI without domain redesign | ✅ |

## Integration notes

- Import: `from services.app import create_app` or `from cohortos import create_app`
- All services share one `DataAccessLayer` instance — required for history, locks, and access evaluation.
- Sync and notifications are optional and degrade gracefully when disabled.
