# Portion 7 — Compile + Non-Technical Handoff Milestone (Phase 4)

**Goal**: Produce a production-ready, installable, fully-integrated single-centre offline domain package (Modules 1–5 + cross-cutting) that can be handed to a non-technical operator for verification and cleanly integrated into Electron (desktop) or FastAPI (cloud/hybrid) without further domain redesign.

**Status target**: Production-ready. All previous 231 tests remain green. New integration surface + docs + packaging + real SQLite path.

## Scope (what “compile + handoff” means)

1. **Durable storage path** — DataAccessLayer gains a real SQLite backend (stdlib `sqlite3`) while preserving the existing in-memory backend for unit tests. Migrations become executable.
2. **Composition root** — Single `CohortOSApp` / `create_app()` that wires every service with correct dependency injection for offline-first (default). One import for integrators.
3. **Migration runner** — `scripts/migrate.py` (or package entry) that applies 001–009 in order against a SQLite file. Idempotent.
4. **Packaging** — `pyproject.toml` + `requirements.txt` (or lock) so `pip install -e .` works. Package name `cohortos` or `cohortos`.
5. **End-to-end integration suite** — New `tests/test_portion7_e2e.py` covering multi-module happy paths + critical [BULLET] edge cases across admission → attendance → payment → exam → content → sync/notify → irregularity → roll migration.
6. **Non-technical handoff artefacts**:
   - `INSTALL.md` — how to install, run migrations, run tests, bootstrap a centre.
   - `HANDOFF.md` — what is ready, what is deliberately deferred (UI, Module 8/9/10), how an Electron or FastAPI layer consumes the package.
   - Updated `BUILD_PLAN.md` + `PORTION_7_SUMMARY.md`.
7. **Hardening only where gaps exist** — no new domain features; only make existing [BULLET]/[LOCKED] items durable, composable, and documented.

## Out of scope (explicit)

- Any UI / Electron / React code.
- Module 8 (Student/Parent accounts) — hard-stop.
- Module 9 (AI) — next portion.
- Module 10 multi-tenant SaaS layer.
- Changing any locked roll-encoding, payment-lock, anti-leak, or bio/manual precedence rules.

## Acceptance criteria

- [ ] `python -m pytest tests/ -q` → all previous + new tests green (target ≥ 250).
- [ ] Real SQLite file can be created, migrated, and used by CohortOSApp; data survives process restart.
- [ ] `CohortOSApp` exposes a stable public surface for the six modules + sync + notification.
- [ ] INSTALL.md and HANDOFF.md exist and are accurate.
- [ ] Package is installable via `pip install -e .` from the portion root.
- [ ] No regression on any [BULLET] or [LOCKED] item from Modules 1–5.
- [ ] Zip `CohortOS_portions_0-7_production.zip` produced under `/home/workdir/artifacts`.

## Build order (small, verifiable steps)

1. Add package skeleton (`pyproject.toml`, `__init__.py`s, requirements).
2. Enhance `DataAccessLayer` with SQLite backend + keep in-memory.
3. Migration runner that executes the 9 SQL files against SQLite.
4. `CohortOSApp` composition root.
5. Bootstrap helper (create centre + default roles + sample batches for origin-client shape).
6. E2E test suite (happy path + edge cases).
7. Docs (INSTALL, HANDOFF, summaries).
8. Full verification + zip.

## Verification commands

```bash
cd /home/workdir/artifacts/cohortos_p7
python -m pytest tests/ -q --tb=line
python -c "from cohortos import CohortOSApp; print('import ok')"
python scripts/migrate.py --db /tmp/cohortos_test.db
```

## Files expected to be created / touched

- `pyproject.toml`, `requirements.txt`, `README.md` (short)
- `cohortos/__init__.py` (or keep flat + package)
- `models/base.py` (SQLite path)
- `services/app.py` (composition root)
- `scripts/migrate.py`
- `tests/test_portion7_e2e.py`
- `INSTALL.md`, `HANDOFF.md`
- `PORTION_7_PLAN.md`, `PORTION_7_SUMMARY.md`, `BUILD_PLAN.md`
- Possibly thin wrappers or `__init__.py` in models/ and services/

Keep the existing flat layout for minimal disruption; only add what is required for installability and composition.
