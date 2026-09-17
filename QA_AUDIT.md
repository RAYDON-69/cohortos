# QA_AUDIT — CohortOS desk (2026-09-17)

Two passes: (A) engineer technical, (B) cold non-technical user. Prior "Batches 1–6 done" is **not trusted**; status below is from re-verification.

## A. Engineer technical pass

| Area | Finding | Severity | Status after this session |
|------|---------|----------|---------------------------|
| Auth refresh API | Backend `/auth/refresh` rotation works 10/10 with persisted refresh JWT | — | Verified live |
| Auth client | Access token memory-only; refresh in localStorage + Electron safeStorage. Race if UI loads before API listens | High | **Fixed**: ensureSession retries; 401/403-only clear; Electron waits for API |
| Error boundaries | No React ErrorBoundary → any throw = white dead screen | Critical | **Fixed**: `ErrorBoundary` wraps all routes |
| Layout scroll | `.app-content` lacked overflow → forms clipped | High | **Fixed**: flex min-height + overflow-y auto |
| Admissions batch dropdown | Only loads on mount; BatchSettings create did not notify Admissions | High | **Fixed**: `cohortos:batches-changed` + focus refetch |
| Analytics paths | Client `/analytics/heatmap` matches server | OK | Verified |
| Storage settings | Returns 200 with `configured: false` for Drive | Medium | Expected until OAuth credentials |
| Google Drive OAuth | No live connection | High product gap | Open |
| SMS provider | Messaging UI only; no provider | High product gap | Open |
| AI tutor/copilot | Screens exist as shells; no agentic data-backed layer | High product gap | Open |
| Automations | Nag list is manual UI, not triggered jobs | High product gap | Open |
| Vault upload | Path-based create; weak open/view | High product gap | Open |
| Biometric UX | Technical pyzk messaging | Medium | Open (simplify pending) |
| Founder billing enforce | Partial license lockout exists; pricing UX incomplete | Medium | Open |
| User AI API keys | Missing | Medium | Open |

## B. Cold first-time user pass (expected friction)

1. **Login clinical** — still OTP-first; not inviting enough (design pass incomplete this session).
2. **"Nag list"** — renamed nav to **Fee reminders**; screen copy may still say nag.
3. **P / A / L** on attendance — expanded to **Present / Absent / Late**.
4. **Settings scatter** — **Settings** hub at `/settings` + Support/legal at `/support`.
5. **Biometric "install pyzk"** — still intimidating for non-technical owners.
6. **Storage "not connected"** — no guided OAuth; feels broken.
7. **No global search** — still missing.
8. **No Contact before Settings hub** — now under Support.

## Reproduction evidence (this session)

### Session persistence (backend)
```
login ok
relaunch refresh 1..10: ok
SESSION PERSIST: 10/10 refresh OK
```
Frontend still depends on storing `refresh_token` (localStorage / safeStorage) and API being up — Electron now waits for `/docs`.

### Endpoints smoke (authenticated)
- GET exams → 200 `{"exams":[]}`
- GET settings/storage → 200
- GET vault → 200
- Attendance batch routes exist under `/t/{id}/attendance/batch/...`

## Not fixed this session (require product decisions or larger builds)
- Full design-token overhaul + global search + login visual redesign
- Agentic AI layer on real centre data
- Automation triggers (cron/outbox workers for fee reminders)
- Real file upload + viewer for vault
- Live SMS provider
- Founder Pricing/Offers + offline license enforcement product rules
- Bring-your-own LLM API keys UI
- Biometric non-technical onboarding rewrite



## Phase 2 update (2026-09-17)

### Engineer
- Vault binary upload/download works in tests without Drive.
- Global search indexes static tabs/features + live students list.
- SMS/Drive still credential-gated.
- AI query is data-grounded local synthesis; not full tool-using agent yet.

### First-time user (expected)
- Login should feel warmer (gradient card) — confirm on device.
- Search box in top bar — try “attendance”, “staff”, a student name.
- Vault: attach file instead of typing a path; use Open/view.
- Settings → AI API keys for BYO key.
- Biometric steps are plain language; still may not auto-sync without device library on host.


## Phase 3 (2026-09-17)

### Engineer
- E2E API harness green (8 tests). License offline seal works.
- npm/vite still unreliable in agent sandbox → GUI screenshot of production React bundle not obtained.

### First-time user
- Login visual direction captured in evidence/login.png (static). Founder should still open real desk for GlobalSearch and vault file picker feel.


## Phase 4
- npm hang explained (proxy 502). Minimal install works on registry.npmjs.org.
- Adversarial suite green (10). Live full React e2e still environment-fragile.


## Phase 5
- RUN_LOCALLY.md for non-expert Linux start.
- Groq/NIM wired; live success blocked by sandbox IP / NIM model availability — see BUILD_LOG.
- Adversarial phase5: rate limit 429, license race, DB safety, automation DST.
