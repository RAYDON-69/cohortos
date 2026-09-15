# CohortOS Frontend — Integrator & Owner Handoff (Portion 24)

**Date**: 2026-08-17  
**Package version**: 0.24.0 (Portions 11–24)  
**Status**: Full UI + API surface production-ready against backend Portions 0–10.

## What is ready

| Persona | Portions | Shell | Status |
|---------|----------|-------|--------|
| Owner / Desk | 12–18 | AppShell | Attendance, admissions, batches, fees, exams, vault, staff, messaging, mode |
| Teacher | 19–20 | AppShell | Review queue, flagged threads, style profile, item bank, OCR beta, cohort insight |
| Student | 21 | MobileShell | Home, Solve (Answer/How/Why), Vault, Results, Threads |
| Parent | 22 | MobileShell | Centre banner, multi-student switcher, per-student prefs/notifs |
| Founder | 23 | AppShell | Dashboard (AI metrics only), provision, suspend/extend, pricing |

**API**: Thin FastAPI routes over tested domain services — no business logic in `api/`.  
**Auth**: JWT bearer for tenant routes; **`X-Founder-Token`** for `/founder/*` only.

## What is deliberately deferred

- Live Gemini SDK (MockLLM remains; real provider is config-swap)
- Payment gateway / SMS provider credentials (templates + channels exist)
- Full Playwright suite against a long-running API (scripts + structure ready; CI wiring is integrators)
- Production Electron code-signing / auto-update
- Parent multi-centre single-login federation (per-centre isolation is by design)

## How a non-technical owner verifies

1. Start backend with durable env:
   - `COACHMATE_JWT_SECRET`
   - `COACHMATE_AUTH_DB` (file path, not `:memory:`)
   - `COACHMATE_CLOUD_DB` (file path, not `:memory:`)
2. From `frontend/`: `npm install && npm run dev`
3. Demo login → walk Attendance → Fees lock → Exam entry → Vault → Teacher review → Student Solve → Parent portal → Founder dashboard.
4. Toggle network off in DevTools: connectivity pill + offline banner must show **Offline · local**, not a spinner forever.
5. Language toggle: EN ↔ বাংলা; layout must not clip at longer Bangla strings.

## How an engineer integrates

```bash
# Backend
cd cohortos_backend
export COACHMATE_JWT_SECRET=... COACHMATE_AUTH_DB=./auth.db COACHMATE_CLOUD_DB=./cloud.db
python -c "from api.main import create_api_app_or_raise; import uvicorn; uvicorn.run(create_api_app_or_raise(), host='127.0.0.1', port=8741)"

# Frontend
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173
npm run build        # dist/
npm run audit:tokens # zero hex outside tokens.css
npm run a11y         # vitest-axe smokes
npm run electron     # COHORTOS_DEV=1 loads Vite + optional local API
```

- Single API client: `src/api/client.ts` (token refresh, 429, offline → sync state).
- Design tokens: `src/tokens.css` only — `npm run audit:tokens` fails on invented hex.
- Shells: `AppShell` (Owner/Desk/Teacher/Founder), `MobileShell` (Student/Parent) — never a third pattern.
- Founder token: `localStorage.cohortos_founder_token` or default `founder-dev-token` (override via `COACHMATE_FOUNDER_TOKEN` on server).

## Design-system compliance (Portion 24 audit)

- **Token drift**: zero `#hex` outside `tokens.css` after hardening pass.
- **Status vocabulary**: attendance / payment / AI badges remain separate classes.
- **Offline**: `SyncPill` four states + `OfflineBanner` on both shells.
- **Large tables**: `DataTable` paginates 25/50/100 — never dumps 6,000 rows unpaginated.
- **Confirm tiers**: inline for light actions; `ModalConfirm` for suspend / destructive.

## Electron packaging smoke

`frontend/electron/main.cjs`:

1. Requires durable `COACHMATE_*` env or skips API spawn with a clear warning.
2. Loads Vite dev URL when `COHORTOS_DEV=1`, else `dist/index.html`.
3. Binds API to `127.0.0.1:8741` when spawned.

## Known notes

- Demo auth stores `cohortos_access_token=demo` — replace with real OTP flow for production.
- OCR assist is intentionally beta/stub — UI never invents grades.
- Founder dashboard **never** shows spend/billing (SPEC §10).

## Files added / changed in Portion 24

- `src/components/OfflineBanner.tsx` + CSS + a11y test
- `src/test/setup.ts`, `vite.config.ts` test block
- `electron/main.cjs`
- `package.json` scripts: `electron`, `audit:tokens`
- Token cleanup across Card/SyncPill/Vault/OCR/Parent/Threads
- `HANDOFF.md`, `PORTION_24_SUMMARY.md`

## Next recommended work

1. Wire Playwright against a durable local API for core offline E2E in CI.
2. Replace MockLLM with Gemini under feature flag.
3. Code-sign Electron builds for centre desktops.
