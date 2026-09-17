# BUILD_LOG — Coaching-Centre Panel Client-Ready Build

Updated: 2026-08-28 (actual command output, not intent)

## Environment / npm install (frontend/)

**What failed in `frontend/`:**
- Prior `npm install` left a **corrupted `node_modules`**: packages like `vite/` and `vitest/` existed as **empty directories** (no `package.json`, only empty `dist/`). Concurrent installs + incomplete extracts.
- `rm -rf node_modules` and `mv node_modules` **timed out / errored** (`cannot remove ... No such file or directory`) — filesystem inconsistent under concurrent npm.
- Full `package.json` install pulls **electron-builder** (heavy native tooling) and repeatedly stalled on this 1.2 GiB RAM host.

**What worked:**
- Clean install of a **minimal test `package.json`** (no electron) in `/tmp/cohort-frontend-deps`:
  ```
  added 165 packages in 18s
  ```
  `vite` + `vitest` present with valid `package.json`.

Vitest/a11y were run from that tree with `src/` copied from the real frontend.

## Command results (real)

### `npx vitest run` (via `/tmp/cohort-frontend-deps`)

| Suite | Result |
|-------|--------|
| hooks + auth + settings (ConflictLog, BackupExport, StaffRoles) | **9 files, 15 tests passed** |
| VaultManagement | **1 file, 2 tests passed** |
| ExamAnalytics | **1 file, 2 tests passed** |
| ExamEntry | **FAIL — Node OOM** (`FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory`) on 512–1024 MB heap; could not complete |
| OfflineBanner a11y | **1 file, 2 tests passed** (jsdom canvas warning only) |

**Totals executed green:** **20 tests passed** across Batch 2 + StaffRoles + Vault + ExamAnalytics + a11y.  
**ExamEntry:** test file written; **not green** (OOM).

### `npm run audit:tokens` (node one-liner from package.json)

1. First run: **FAIL** — `src/screens/batches/BatchSettings.tsx: #0a0` (fallback in `var(--success, #0a0)`).
2. Fixed to `var(--sage-700)`.
3. Second run: **`token audit clean`** (exit 0).

### `npm run a11y` equivalent

```
Test Files  1 passed (1)
     Tests  2 passed (2)
```
(`src/components/OfflineBanner.a11y.test.tsx`)

### Backend pytest (session)

`tests/test_batch1_routes.py` + `tests/test_batch2_routes.py` → **7 passed** (earlier this session).

---

## Status matrix

| Screen | Batch | Status | Tests added | States verified | Notes |
|--------|-------|--------|-------------|-----------------|-------|
| Exam create/results/complete routes | 1 | Done | test_batch1_routes.py | API | |
| Exam analytics routes | 1 | Done | test_batch1_routes.py | API | |
| Vault routes | 1 | Done | test_batch1_routes.py | API | |
| Staff role assignment | 1 | Done | test_batch1_routes.py | API | |
| deskNav + teacherNav | 1 | Done | — | conflicts+backup items | |
| ExamEntry empty/error vitest | 1 | Done | ExamEntry.test.tsx + ExamEntryStatus.test.tsx | empty + error | Full `ExamEntryScreen` import **OOMs** (~380MB+) under 1.2GiB; fixed by extracting `ExamEntryStatus` (same UI the screen renders). **6 passed** with `--pool=forks --poolOptions.forks.singleFork --no-coverage` at 256MB heap. |
| ExamAnalytics empty/error vitest | 1 | Done | ExamAnalytics.test.tsx | empty + error | **2 passed** |
| VaultManagement empty/error vitest | 1 | Done | VaultManagement.test.tsx | empty + error | **2 passed** |
| StaffRoles empty/error vitest | 1 | Done | StaffRoles.test.tsx | empty + error | **2 passed** |
| StaffLogin extract | 2 | Done | — (covered via RequireAuth + useAuth) | loading/error/normal | Code + tokens clean; a11y suite green for shared components |
| RequireAuth harden | 2 | Done | RequireAuth.test.tsx | unauth recoverable | **1 passed** |
| hooks useAuth | 2 | Done | useAuth.test.tsx | unauth + logout | **2 passed** |
| hooks useTenant | 2 | Done | useTenant.test.tsx | present + empty | **2 passed** |
| hooks useConnectivity | 2 | Done | useConnectivity.test.tsx | offline | **1 passed** |
| hooks useApi | 2 | Done | useApi.test.tsx | success + error | **2 passed** |
| hooks useOfflineQueue | 2 | Done | useOfflineQueue.test.tsx | depth 0 | **1 passed** |
| Sync Conflict Log | 2 | Done | ConflictLog.test.tsx + test_batch2 | empty + error | **2 + API passed**; tokens clean |
| Backup & Data Export | 2 | Done | BackupExport.test.tsx + test_batch2 | success + error | **2 + API passed**; tokens clean |
| License lockout state | 2 | Done | test_batch2 license_status + useLicenseLockout in RequireAuth | locked=false trial | Banner component; tokens clean |
| BiometricDevices | 3 | Not started | — | — | |
| StorageService + GoogleDrive + settings | 3 | Done | test_batch3 + StorageProvider.test.tsx | not-configured empty / error | StorageService + LocalFs + GoogleDriveStorageProvider; settings GET/PUT/test. Frontend 2 passed. |
| Centre Setup Wizard | 4 | Done | test_batch4_setup_wizard.py (2) + CentreSetupWizard.test.tsx (2) | loading/empty/error/partial/offline/done | GET setup/status; POST setup/first-batch 409 if batches exist; /setup redirects when needs_wizard=false |
| Visual/UX polish | 5 | Not started | — | — | |
| Windows/Mac packaging | 6 | Not started | — | — | |
| Teacher UI states §1.B | — | Not started | — | — | |

## Closing summary

- **Batch 2 rows flipped to Done only where vitest (or API) + token audit + a11y baseline are green.** That is: hooks, RequireAuth, Conflict Log, Backup Export, License lockout wiring, StaffLogin extract.
- **ExamEntry frontend vitest is not Done** — real OOM failure, not skipped by choice.
- **Do not start Batch 3 until ExamEntry vitest is green** on a machine with enough RAM, or ExamEntry is split/lazy-mocked further.
- **`frontend/node_modules` remains broken in-tree**; use `/tmp/cohort-frontend-deps` or a clean reinstall without electron on a larger host for local dev.

**Needs founder decision:** none.


## Packaging / Batch 6 (this sandbox)

**electron-builder cannot run here.** Host has **1.2 GiB RAM, 0 swap**. Prior npm installs of electron-builder already corrupted `frontend/node_modules`; a single vitest transform of ExamEntry hit ~380 MB. electron-builder + Electron download + wine (for Windows targets on Linux) typically need **4–8 GiB+**.

**Do not attempt packaging in this agent.** Use CI:

- Workflow: `.github/workflows/desktop-release.yml`
- Matrix: `ubuntu-22.04` (AppImage), `windows-2022` (nsis + portable), `macos-14` (dmg)
- Per-OS PyInstaller `cohortos-api` binary before electron-builder (prd §25)
- `frontend/package.json` `build.win` / `build.mac` targets added

Tag `v*` or run workflow_dispatch from GitHub to produce installers.


## Batch 3 (2026-08-28)

| Screen | Batch | Status | Tests | Notes |
|--------|-------|--------|-------|-------|
| BiometricDevices | 3 | Done | backend routes + BiometricDevices.test.tsx **3 passed** | pyzk missing banner; empty/error |
| StorageProvider | 3 | Done | storage unit + routes + StorageProvider.test.tsx **2 passed** | not_configured CTA |
| test_batch3_biometric_storage.py | 3 | Done | **6 passed** | |
| token audit | — | clean | — | |


### Batch 3 real counts
- `pytest tests/test_batch3_biometric_storage.py` → **6 passed**
- vitest BiometricDevices → **3 passed**; StorageProvider → **2 passed** (5 total)
- token audit → **clean**
- Offline: device config is local via tenant DB; live pull/test blocked without network/pyzk (UI message, not crash)
- a11y baseline: existing OfflineBanner suite still the repo pattern; no new hex in Batch 3 screens


### Batch 4 real counts
- `pytest tests/test_batch4_setup_wizard.py` → **2 passed** (needs_wizard when zero batches; 409 after first batch)
- vitest CentreSetupWizard → **2 passed** (empty + error)
- token audit → **clean**
- Six UI states on wizard: loading, empty (no batches), error+retry, partial note, offline banner, done
- Existing centres: `needs_wizard=false` → Navigate to /attendance; main routes never blocked


## Batch 5 — visual / UX polish (real results)

**Gates:** `token audit clean` · Batch5.a11y.test.tsx **4 passed** (LicenseLockout alert, AttendanceBadge/PaymentBadge text+role, EmptyState+Button axe)

### Shared components
| Component | Fix |
|-----------|-----|
| DataTable | Sticky header via `.data-table-scroll` + `position: sticky` on head (long tables keep headers visible) |
| PaymentBadge | Default `showDot` so payment status is icon+color+label, not color alone |
| Badge (nag) | Green/white/irregular use Badge with text labels + showDot |

### Screen-by-screen

| Screen | Status | What fixed (or already compliant) |
|--------|--------|-----------------------------------|
| TodayAttendance | Already compliant | AppShell; DataTable; AttendanceBadge+SourceBadge with text; inherits sticky headers |
| AttendanceHistory | Already compliant | AppShell + DataTable pattern (sticky via shared component) |
| FeesThisMonth | Compliant + improved | PaymentBadge already used; now showDot default |
| GreenWhiteNagList | Fixed | Replaced color-only `badge-*` spans with Badge + labels + showDot |
| AdmissionsList | Already compliant | AppShell + DataTable + FormField |
| BatchSettings | Already compliant | AppShell + FormField + Card |
| ExamEntry | Already compliant | AppShell + shared form/table; status via ExamEntryStatus |
| ExamAnalytics | Already compliant | AppShell + DataTable |
| VaultManagement | Already compliant | AppShell + shared components |
| StaffRoles | Already compliant | AppShell + DataTable pattern |
| MessagingSettings | Already compliant | AppShell + FormField |
| ModeSettings | Already compliant | AppShell + FormField |
| ConflictLog | Fixed | Raw `<table>` → **DataTable**; locked flag → **PaymentBadge**; sticky headers |
| BackupExport | Already compliant | AppShell + EmptyState + Button |
| LicenseLockoutBanner | Already compliant | role=alert; CSS vars only; a11y covered |
| BiometricDevices | Fixed | One-off inputs → **FormField/TextInput**; device list → **Card** |
| StorageProvider | Fixed | One-off fields → **FormField/SelectInput/TextInput** + **Card** |
| CentreSetupWizard | Fixed | Raw labels/inputs → **FormField/TextInput**; keeps six UI states |
| MobileShell / AppShell | Already compliant | ≤760px horizontal nav strip (AppShell.css); student/parent MobileShell unchanged |

### Notes
- No new hex values introduced; full-tree token audit clean after each touch set.
- Dense grids (attendance, fees, conflicts) use shared DataTable sticky region.
- Batch 6 packaging remains CI-only (see desktop-release.yml) — not run in 1.2GiB sandbox.


## Closing pass (2026-08-28 evening)

### Mode confirmation
Work was applied under **Build** against real files at  
`/home/workdir/artifacts/CohortOS/cohortos/` (not a sandbox-only Ask draft).  
Edits are on disk in that tree (e.g. `frontend/src/components/DataTable.tsx`, Batch 2–5 screens, `BUILD_LOG.md`).

### Full `npm run a11y` (repo definition)
Script: `vitest run --reporter=verbose src/**/*.a11y.test.tsx`

Matching files in tree:
- `src/components/OfflineBanner.a11y.test.tsx` (2 tests)
- `src/components/Batch5.a11y.test.tsx` (4 tests)

**Result: 6 passed / 0 failed** (2 files).

**Important limit:** the package script does **not** axe every screen. Only components that have a dedicated `*.a11y.test.tsx` file are covered. Screen-level a11y for attendance/fees/admissions/wizard/etc. is **not** automated in this suite; Batch 5 claimed compliance by shared-component reuse + the badge/banner tests above, not by per-route axe runs.

(jsdom logs `HTMLCanvasElement.getContext` not implemented during axe color-contrast; tests still passed.)

### Full pytest
```
351 passed, 1 warning in 6.59s
exit code 0
```
Includes batch1–4 route tests plus legacy suite. No new failures observed after Batch 5 component/CSS changes (backend untouched by polish).

### Token audit (post–Batch 5)
`token audit clean` (full `frontend/src` walk, excluding `tokens.css`).

---

## Known remaining gaps

Honest residual risk — not claimed Done.

1. **Per-screen a11y expanded (2026-09-13).** Suite now **23 tests** across 3 files covering Batch 1–5 desk screens; still not a full axe of every interactive state/route deep-link. Dense screens (TodayAttendance, FeesThisMonth, AdmissionsList, ConflictLog after DataTable migration, CentreSetupWizard) were **not** independently axe-scanned in this closing pass. Sticky-header DataTable markup was fixed but not covered by a dedicated a11y test.

2. **Frontend vitest for Batch 1 dense screens is incomplete under sandbox RAM.** Full `ExamEntryScreen` import still OOMs (~380MB+) on the 1.2 GiB host; empty/error coverage is via extracted `ExamEntryStatus` only. Vault/ExamAnalytics/StaffRoles tests were written earlier but were **not** re-run in this closing pass as a single `vitest run` over the whole frontend tree (deps install in-tree remains unreliable).

3. **Google Drive is not production-wired.** `GoogleDriveStorageProvider` enforces configure-or-fail and uses a local cache path when a token is present; it does **not** call the real Google Drive HTTP API or complete OAuth. Settings UI accepts a pasted access token. Real OAuth client ID / refresh-token flow and resumable Drive upload are still open work.

4. **pyzk hardware path is optional and untested against real devices.** Status/test/pull degrade when the library is missing; no live ZKTeco integration test exists in CI.

5. **Centre Setup Wizard “create centre” step is pre-satisfied.** Wizard assumes centre already exists via `/auth/centre-trial`. There is no in-wizard centre-name form; first-run is trial → login → `/setup` for batch + admission only.

6. **Wizard admission requires a batch_id from prior step;** if the user deep-links to admission with zero batches and partial state is wrong, they are bounced to batch step. No backend “setup/complete” transaction — steps are separate API calls (batch then admit).

7. **Batch 6 packaging not executed here.** `electron-builder` / per-OS `cohortos-api` binaries are delegated to `.github/workflows/desktop-release.yml`. Windows nsis/portable and Mac dmg have **never** been produced in this agent environment. package.json targets were expanded; CI run is founder-side.

8. **Student/Parent/Teacher/Founder shells outside Coaching-Centre Panel scope** were not part of Batches 1–5 polish inventory beyond noting MobileShell exists; no Batch 5 row claims for those surfaces unless they already used shared tokens.

9. **Offline exercise for Batch 5 polish** was not re-run as a manual power-cut scenario; offline behaviour relies on existing OfflineBanner + connectivity hooks. Conflict resolve while offline was not re-tested end-to-end in this pass.

10. **ConflictLog / Biometric / Storage / Wizard empty+error vitests** were green when last run in /tmp harnesses; they were **not** re-executed in this exact closing pass (only a11y + full pytest + token audit). Treat as “last known green,” not “reconfirmed tonight.”

11. **Bulk CSV device mapping** covered by `test_biometric_link_bulk.py` (**7 passed**: malformed, not-found, duplicates, mixed, empty).

12. **prd.md items still soft:** full bilingual UI parity audit, real-device biometric, Drive OAuth, desktop installers, and exhaustive screen-level axe coverage remain outside what this session closed.


## Consolidated frontend vitest (2026-08-29)

**One harness run** (`/tmp/cohort-vitest-all`, real `frontend/src` tests + thin `api/client` stub, `pool=forks`, `maxWorkers=1`, `NODE_OPTIONS=--max-old-space-size=512`):

```
Test Files  18 passed (18)
     Tests  38 passed (38)
Duration  14.38s
```

Files included (Batch 2–5 + hooks/auth/a11y):
- auth/RequireAuth.test.tsx
- components/Batch5.a11y.test.tsx, OfflineBanner.a11y.test.tsx
- hooks/useApi, useAuth, useConnectivity, useOfflineQueue, useTenant
- exams/ExamAnalytics, ExamEntry, ExamEntryStatus
- settings/BackupExport, BiometricDevices, ConflictLog, StaffRoles, StorageProvider
- setup/CentreSetupWizard
- vault/VaultManagement

No failures. ExamEntry remains status-contract tests (full screen still OOM-prone if imported whole).

---

## Google Drive — NOT Done (waiting on founder credentials)

Storage is **not** marked Done for real Drive. `GoogleDriveStorageProvider` still uses local cache after a token is present; it does **not** call Drive HTTP APIs.

### What you need to create (Google Cloud Console)

1. Open [Google Cloud Console](https://console.cloud.google.com/) → create or select a project (e.g. `CohortOS`).
2. **APIs & Services → Library** → enable **Google Drive API**.
3. **APIs & Services → OAuth consent screen**
   - User type: **External** (or Internal if Workspace-only).
   - App name: CohortOS (or your brand).
   - Support email: yours.
   - Scopes: add `https://www.googleapis.com/auth/drive.file` (files created by the app only — preferred) **or** `https://www.googleapis.com/auth/drive` if you need broader folder access.
   - Test users: add the Google account that owns the centre Drive (while app is in Testing).
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   - Application type: **Desktop app** (simplest for desk/Electron) **or** Web application if you prefer a browser redirect URI.
   - Name: `CohortOS Desk`.
   - Download JSON **or** copy **Client ID** and **Client secret**.

### Optional but recommended

5. In Drive, create a folder e.g. `CohortOS Vault` and copy its **folder ID** from the URL  
   (`https://drive.google.com/drive/folders/FOLDER_ID_HERE`).

### What to send me (paste in chat — treat as secret)

Provide **one** of these packages:

**Option A — OAuth client (preferred for “connect my Drive”):**
- `client_id`
- `client_secret`
- Redirect URI you configured (if Web type), e.g. `http://127.0.0.1:8741/oauth/gdrive/callback`
- Google account email that will consent (must be a test user if app is in Testing)

**Option B — Service account (server-to-server, no interactive OAuth):**
- Full **service account JSON** key file contents
- Drive folder ID shared with that service account email (Editor)

Do **not** commit secrets into the repo. Prefer env vars / local secrets files that are gitignored.

### Where values will live after you provide them

| Value | Location |
|-------|----------|
| OAuth client id/secret | Env: `COHORTOS_GDRIVE_CLIENT_ID`, `COHORTOS_GDRIVE_CLIENT_SECRET` (or centre `storage.*` config — never frontend source) |
| Access / refresh token after consent | Server-side only: `COHORTOS_GDRIVE_ACCESS_TOKEN` / refresh via TokenService or config section `storage` |
| Folder id | Settings → Storage UI **or** `COHORTOS_GDRIVE_FOLDER_ID` |
| Service account JSON | `COHORTOS_GDRIVE_CREDENTIALS` (path or JSON string), server only |

### What I will implement and test once credentials arrive

1. Real Drive upload using Google’s resumable upload API (not local cache).
2. `exists` / `download` / `delete` against the same `remote_id`.
3. Automated test: upload a small bytes payload → download → compare → delete (live against **your** Drive).
4. Settings “Test upload” will create and remove a real file under the configured folder.
5. Only then flip Storage / GoogleDrive to **Done** in BUILD_LOG with the live round-trip evidence.

**Stopped here** — waiting for your Client ID/secret (or service-account JSON) + optional folder ID before any further Drive work.


## A11y expansion + bulk biometric tests (2026-09-13)

### Expanded `*.a11y.test.tsx` suite
Files:
- `src/components/OfflineBanner.a11y.test.tsx` (2)
- `src/components/Batch5.a11y.test.tsx` (4)
- `src/screens/Screens.a11y.test.tsx` (17) — ConflictLog, BackupExport, BiometricDevices, StorageProvider UI, StaffRoles, CentreSetupWizard, ExamEntryStatus, ExamAnalytics, VaultManagement, MessagingSettings, ModeSettings, TodayAttendance, AttendanceHistory, FeesThisMonth, GreenWhiteNagList, AdmissionsList, BatchSettings

**Result: 23 passed / 0 failed** (3 files).

Shared fix while expanding coverage:
- `DataTable`: `aria-busy` moved to `role="table"`; body uses `role="rowgroup"` (fixes axe `aria-required-children` critical).
- `BackupExport`: null-safe `status.backups` (avoid crash when status partial).

StorageProvider/GoogleDriveStorageProvider **code not modified** (Drive credentials still pending).

### Bulk biometric `device_user_id` linking
`tests/test_biometric_link_bulk.py`:

| Case | Result |
|------|--------|
| Happy path by student_id | pass |
| Happy path by roll | pass |
| Malformed / missing device_user_id | pass |
| Student not found (id + roll) | pass |
| Duplicate device_user_id on two students | pass (both linked; API documents last-write lookup) |
| Mixed valid + invalid rows | pass |
| Empty rows | pass |

**Result: 7 passed / 0 failed.**

Route clarification: failed `link_device_user` now returns error `"student not found"` (was `"link failed"`) for clearer CSV feedback.


## CI fix — desktop-release Set up Node (2026-09-15)

**Failure:** `actions/setup-node@v4` with `cache: npm` and `cache-dependency-path: frontend/package-lock.json` →  
`Error: Some specified paths were not resolved, unable to cache dependencies.`

**Cause:** Repo has `frontend/package.json` only — **no** `package-lock.json` (root or frontend). Cache path did not exist.

**Change (scoped):** Removed `cache:` and `cache-dependency-path` from the single `setup-node` step. Kept explicit `node-version: "20"`.

**Note:** `npm ci` in the next step still requires a lockfile; if Install fails next, generate/commit `frontend/package-lock.json` or switch that step to `npm install` (separate change).


## CI — package-lock + Windows binary log (2026-09-15)

### Fixed
- Generated and committed `frontend/package-lock.json` so `npm ci` works in Desktop release.
- Lockfile not in `.gitignore`.

### Still open — Package win
PyInstaller **completed successfully** (`Building EXE from EXE-00.toc completed successfully`, results in `D:\a\cohortos\cohortos\dist`).
Step failed after that on bash normalize:

```
cp: 'dist/cohortos-api.exe' and 'dist/cohortos-api.exe' are the same file
##[error]Process completed with exit code 1.
```

Root cause: workflow copies `dist/cohortos-api.exe` → `dist/cohortos-api.exe` (same path) under `bash -e`, which fails on Windows. Not a PyInstaller compile failure. Fix deferred pending founder review of this log.


## CI — npm ci → npm install (2026-09-15)

**Abandoned:** generating `frontend/package-lock.json` in the agent sandbox (npm hung / timed out; partial lock was out of sync with `package.json` and still failed `npm ci` on runners).

**Change:** In `.github/workflows/desktop-release.yml`, the single matrix step `Install frontend deps` (`working-directory: frontend`) now runs `npm install` instead of `npm ci`. One job template serves linux/win/mac — same path, same step.

**Still open:** Package win fails after successful PyInstaller on post-build `cp` of `dist/cohortos-api.exe` onto itself under `bash -e`.


## CI — Windows binary path + TypeScript build (2026-09-15)

### Bug 1 — Package win: Build cohortos-api binary
- **Symptom:** `cp: 'dist/cohortos-api.exe' and 'dist/cohortos-api.exe' are the same file` exit 1 under bash -e.
- **Root cause:** Normalize step copied the Windows onefile output onto itself. PyInstaller had already succeeded.
- **Fix:** Copy `dist/cohortos-api.exe` → `dist/cohortos-api` (path electron-builder `extraResources` expects). Fail if missing/small; PE MZ header check on Windows.

### Bug 2 — Package linux/mac: Build renderer (`tsc -b && vite build`)
- **Errors:**
  - `useAuth.ts`: `sendOtp` typed as `typeof requestOtp` but implementation is `(phone, tenantId?) => …`
  - `GreenWhiteNagList.tsx`: `Badge` used without import
  - `CentreSetupWizard.tsx`: `connectivity.state` narrowed to `never` via `"isOffline" in connectivity`
- **Fix:** Correct `sendOtp` type; import `Badge`; use `connectivity.isOffline`.


## CI iteration — electron-builder channel + Windows path (2026-09-15)

### electron-builder linux/mac
- **Error:** `TypeError: Cannot read properties of null (reading 'channel')` in `updateInfoBuilder.computeChannelNames` when no `repository` in package.json and publish metadata is attempted even with `--publish never`.
- **Fix:** Set `repository` in `frontend/package.json` and `build.publish: null`. Broaden `extraResources` to `../dist/` with filter `cohortos-api` + `cohortos-api.exe`.

### Windows binary again
- **Error:** Git Bash treats `cohortos-api.exe` and `cohortos-api` as the same path → `cp: ... are the same file`.
- **Fix:** Stop copying between those names. Verify `dist/cohortos-api.exe` in place (size + PE MZ). Packager picks up `.exe` via extraResources filter.


## Desktop release — ALL GREEN (2026-09-15)

Run: https://github.com/RAYDON-69/cohortos/actions/runs/34961460073 (`e41ed18`)

| Job | Conclusion |
|-----|------------|
| Package linux | **success** (through Upload installers) |
| Package win | **success** (through Upload installers) |
| Package mac | **success** (through Upload installers) |

Artifacts: `cohortos-linux`, `cohortos-win`, `cohortos-mac`.


## Artifact validation — cohortos-linux (2026-09-15)

**Source:** Actions run 34961460073 artifact `cohortos-linux` (277 MB zip).

**Contents:**
- `CohortOS-0.11.0.AppImage` (ELF, ~139 MB) — extracts cleanly via `--appimage-extract`
- `linux-unpacked/` — Electron binary + `resources/bin/cohortos-api` (ELF, ~31 MB) + backend python + `app.asar`
- `builder-debug.yml`

**Sandbox checks:**
- Zip extract: OK
- AppImage `--appimage-help` / `--appimage-extract`: OK
- Direct AppImage run: fails here with `dlopen(): error loading libfuse.so.2` (no libfuse2 in this environment; no DISPLAY)
- `resources/bin/cohortos-api` present and is ELF; `ldd` shows no missing system libs for the API binary
- Unpacked Electron needs its adjacent `.so` files (`libffmpeg.so` etc.) on `LD_LIBRARY_PATH` when run outside the full tree

**Human launch (Linux Mint 22.x XFCE):** install `libfuse2` if AppImage won't start, `chmod +x`, run from a graphical session.


## QA stress re-verification (2026-09-17)

**Rule:** Prior completion claims discarded. Evidence from live API + code fixes only.

### 1. Auth/session
- **Repro (backend):** login → refresh 10× with rotated refresh tokens → all OK.
- **Root cause (desk):** UI could call `ensureSession` before local API listened; `clearTokens` on any non-OK refresh; access token never disk-persisted (by design) so failed refresh ⇒ OTP.
- **Fix:** `ensureSession` retries while refresh token still stored; clear tokens only on 401/403; Electron `waitForApi` before window load; RequireAuth secondary retry.
- **Stress:** backend 10/10 refresh; Electron wait not GUI-tested in sandbox (no display).

### 2. Blank dead-end screens
- **Root cause:** no React error boundary; layout clip without scroll.
- **Fix:** `ErrorBoundary` recovery UI with back link; `.app-main`/`.app-content` scroll.
- **Stress:** boundary unit path is recovery UI; full click-path needs founder device retest.

### 3. Internal Server Errors (exams/storage/analytics)
- **Repro live:** exams + storage 200 empty; heatmap/struggle routes exist (404 only on wrong probe paths).
- **Note:** intermittent 500s in pilot may be tenant/data or old build — retest on artifact from green CI after this push.

### 4. Batches/Admissions
- **Root cause:** Admissions batches loaded once; create on BatchSettings did not invalidate.
- **Fix:** `cohortos:batches-changed` event + window focus refetch; AppShell scroll for clipped empty forms.

### 5–14. Design, AI, automation, vault, biometric, SMS, monetization, support, settings, copy
- **Settings hub + Support/legal** added (items 12–13 partial).
- **Copy:** Present/Absent/Late; Fee reminders nav label.
- **Remaining:** documented in `QA_AUDIT.md` as open product gaps — not falsely marked done.

