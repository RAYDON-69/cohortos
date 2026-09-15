# PRD.md — CohortOS (CoachMate) Full Product & Interaction Specification

**Version:** 2.0 — Workflow-Complete / Production Bar  
**Product name in UI:** CohortOS (legacy code/docs may still say CoachMate; treat as the same product)  
**Companion documents:**
- `SPEC_v3.md` — business rules, edge cases, `[LOCKED]` / `[HARDENED v3]` (source of truth for *what is allowed*)
- This `PRD.md` — *who does what, in what order, which screen, which API, when it is done*
- Codebase: `api/`, `services/`, `frontend/src/screens/`, `electron/`

**Rule:** Nothing is “done” because a screen renders. A flow is done only when every step below has loading / empty / populated / error / offline states, the listed API exists and is tested, and RBAC is enforced server-side.

---

## 0. How to read this document

| Symbol | Meaning |
|--------|---------|
| **Screen** | Named UI surface (route in app) |
| **User does** | Exact control the person taps/types |
| **System does** | What the UI must show next |
| **API** | HTTP call the client must make (path relative to API base, usually `http://127.0.0.1:8741` on desktop) |
| **Auth** | Bearer access JWT unless noted; refresh via `/auth/refresh` |
| **Roles** | `owner` · `desk` · `teacher` · `assistant` · `student` · `parent` · `founder` |
| **Phase** | P1 = pilot desk (must ship first) · P2 = vault + student/parent · P3 = AI hardened + multi-currency |

Navigation must **never trap** the user: every authenticated desk screen shares the same primary nav. Settings may add secondary tabs but must keep primary nav + “← Back to desk”.

---

## 1. Product snapshot (honest)

### 1.1 What exists in code today (domain + routes)

**Domain services (tested logic):** admission, attendance, payment, exam, content/vault, sync, notification, accounts, AI solve/teach stubs, founder admin, pricing.

**HTTP surface (examples):**  
`/auth/*`, `/t/{tenant_id}/batches|students|attendance|payments|exams|vault|staff|settings/*|solve/ask|ai/*`, `/founder/*`, `/sync/push|pull`, `/health`, `/me`.

**Frontend screens:** Admissions, Batches, Attendance (today + history), Fees (+ nag list), Exams (+ analytics), Vault, Settings (staff/messaging/mode), Teacher set (style, OCR, review, item bank, threads, insight), Student set, Parent portal, Founder set.

### 1.2 What is *not* client-ready yet (do not claim otherwise)

1. Many teacher/student/AI screens call APIs that are partial or return empty shells.  
2. Frontend↔backend contract drift still possible on Group A routes (migrate, some exam/vault/AI endpoints).  
3. Real SMS is not production; pilot may show OTP on screen.  
4. Packaging: Linux AppImage exists; Windows/Mac signed installers and Android native are incomplete.  
5. Full offline cold-start on every OS not fully UAT-proven in field.

**Build order (locked by this PRD):** finish **§3 desk P1 workflows** + packaging before expanding AI or new modules.

---

## 2. Global product rules (all surfaces)

### 2.1 Session & auth

| Event | Behavior |
|-------|----------|
| First login on a device | Phone (or email) → OTP → tokens issued |
| Access token | Short-lived, **memory only** in client |
| Refresh token | Long-lived (~30 days); stored securely (Electron safeStorage + localStorage fallback); **returned in JSON** on verify/refresh so desktop survives reboot |
| App restart | Call `POST /auth/refresh` with stored refresh → new access → enter last role home; **do not** force OTP if refresh succeeds |
| Explicit logout | `POST /auth/logout` → clear tokens → login screen |
| Multi-centre phone | `POST /auth/request-otp` without tenant returns `centres[]`; user picks centre; second request includes `tenant_id` |

**OTP (SPEC):** 6 digits, ~10 min expiry, attempt limits, rate limits per phone and IP.  
**Pilot:** if SMS provider unset, UI **must** display `_test_code` from API response (never require terminal).

### 2.2 Primary navigation (Owner / Desk / Teacher — authenticated)

Always visible (same order on every desk screen):

1. **Attendance** → `/attendance`  
2. **History** → `/attendance/history`  
3. **Admissions** → `/admissions`  
4. **Batches** → `/batches`  
5. **Fees** → `/fees`  
6. **Exams** → `/exams`  
7. **Settings** → `/settings/mode` (or staff)

Optional secondary (role-gated): Vault, Teacher tools, Founder.  
**Brand “CohortOS”** click → `/attendance`.  
Settings sub-tabs: Staff | Messaging | Mode + **← Back to desk**.

### 2.3 Five UI states (every list/form screen)

1. **Loading** — skeleton or disabled controls, not infinite blank  
2. **Empty** — clear copy + primary CTA (e.g. “No batches yet → Create batch”)  
3. **Populated** — data table/cards  
4. **Error** — message + Retry  
5. **Offline** — OfflineBanner / SyncPill; core writes queue; no “broken” empty crash  

### 2.4 Language

English first; Bangla toggle. All user-visible strings via i18n (`strings.ts`). No hard-coded English-only paths for staff-facing P1.

### 2.5 Tenant isolation

Every data route is under `/t/{tenant_id}/...`. JWT carries `tenant_id`. Cross-tenant access → **403**. Founder metrics-only unless consented support access (SPEC §10).

---

## 3. Surface A — Coaching desk (Owner / Desk staff) — PHASE 1 CORE

This is the product a Barishal centre must use daily. **All flows in this section are P1.**

### 3.0 First-run: centre trial (cold start)

**Screen:** Login / Trial (`/login`)

| Step | User does | System does | API |
|------|-----------|-------------|-----|
| 1 | Opens app | Login card: Sign in · Start free trial | `GET /health` (optional readiness) |
| 2 | Taps **Start free trial** | Fields: Centre name, Owner phone, Owner name (optional) | — |
| 3 | Submits | Creates tenant + owner account; starts 14-day trial | `POST /auth/centre-trial` body `{ centre_name, owner_phone, owner_name? }` |
| 4 | Success | Auto-request OTP for that phone + tenant | `POST /auth/request-otp` `{ phone, tenant_id }` |
| 5 | Sees code | Pilot: show `_test_code` on screen; production: SMS | Response may include `_test_code` |
| 6 | Enters 6 digits → Verify | Session established | `POST /auth/verify-otp` `{ otp_id, code, tenant_id }` → `access_token`, `refresh_token`, `account_id`, `tenant_id`, `roles` |
| 7 | — | Persist refresh; navigate **Attendance** | Client `saveTokens` |

**Empty first desk (mandatory UX):**  
If zero batches: Attendance shows empty state **with button → Batches**.  
Do not strand user on “No batches” with no path.

**Acceptance:** One path, no tenant ID typing, no founder manual DB insert, OTP visible in pilot, refresh survives restart.

---

### 3.1 Returning staff sign-in

| Step | User does | System does | API |
|------|-----------|-------------|-----|
| 1 | Enters phone → Sign in | Request OTP | `POST /auth/request-otp` `{ phone }` |
| 2a | Single centre | OTP field | May return `otp_id` immediately |
| 2b | Multiple centres | List centres; user selects one | Response `centres: [{ tenant_id, centre_name, role }]` |
| 3 | After select | Request OTP again | `POST /auth/request-otp` `{ phone, tenant_id }` |
| 4 | Enter code → Verify | Home by role | `POST /auth/verify-otp` … |
| 5 | Restart app later | Silent refresh | `POST /auth/refresh` `{ refresh_token }` or cookie |

---

### 3.2 Batches — create & configure

**Screen:** Batch settings (`/batches`)  
**Roles:** owner, desk (create); teacher read as needed  

#### 3.2.1 Create batch

| Step | User does | System does | API |
|------|-----------|-------------|-----|
| 1 | Opens Batches | List existing batches or empty CTA | `GET /t/{tid}/batches` |
| 2 | Fills name, days (Sat–Fri checks), hour 0–23 | Validation | — |
| 3 | **Create batch** | New batch in list; select it | `POST /t/{tid}/batches` `{ name, days[], hour }` → `batch_id` / batch object |
| 4 | Optional: late override, extra session | Save controls | `PUT/POST` late-threshold & extra-session endpoints as implemented |

**Roll encoding (SPEC, system-side on admit):** DaySet bitmask + TimeCode + serial per (DaySet, TimeCode); collision suffix `-A`/`-B` when two batches share slot.

**Acceptance:** Create without terminal; batch appears in Attendance and Admissions dropdowns after refresh.

---

### 3.3 Admissions — add students

**Screen:** Admissions (`/admissions`)  
**Roles:** owner, desk  

| Step | User does | System does | API |
|------|-----------|-------------|-----|
| 1 | Open Admissions | Student list + form | `GET /t/{tid}/students`, `GET /t/{tid}/batches`, `GET /t/{tid}/templates` |
| 2 | Select batch | Roll preview | `GET /t/{tid}/students/roll-preview?batch_id=` (or POST body as implemented) |
| 3 | Name + **student phone** (+ parent phone optional) | — | — |
| 4 | Optional **Check duplicates** | Show matches / clear | `POST /t/{tid}/students/duplicate-check` `{ name, student_phone }` — **student phone only**, not parent |
| 5 | **Admit** | Row added; join code shown if returned | `POST /t/{tid}/students` `{ name, batch_id, phone, parent_phone? }` |
| 6 | Sibling student phone | Block with reason | Same duplicate rules |
| 7 | Sibling parent phone, different students | Allowed (siblings) | — |

**Migrate batch/roll (when UI wired):**  
`POST /t/{tid}/students/{id}/migrate` (or documented path) → full history moves (SPEC `[BULLET]`).

**Acceptance:** Two siblings same parent phone OK; same student phone blocked with explicit reason.

---

### 3.4 Attendance — today

**Screen:** Today attendance (`/attendance`)  
**Roles:** owner, desk, teacher (mark per policy)  

| Step | User does | System does | API |
|------|-----------|-------------|-----|
| 1 | Open Attendance | Batch select + date (default today) | `GET /t/{tid}/batches` |
| 2 | Choose batch | Grid of enrolled students | `GET /t/{tid}/attendance/batch/{batch_id}?date=` or `GET /t/{tid}/attendance?batch_id=&date=` |
| 3 | Tap status P / L / A | Cell updates (optimistic + save) | `POST /t/{tid}/attendance/manual` `{ batch_id, date, student_id, status }` |
| 4 | Biometric available | Pull / status indicators | `GET .../biometric/status`, `POST .../biometric/pull` |
| 5 | Conflict / anti-proxy | Review queue | `GET .../attendance/reviews`, `POST .../reviews/{id}/resolve` |

**Rules (must match SPEC, enforced backend):**  
- Late after threshold (default 12 min); upper cutoff → absent  
- Biometric authoritative; manual fills gaps only  
- Cross-batch only if student enrolled in that batch  

**Empty states:** No batch → CTA to Batches. Batch with no students → CTA to Admissions.

---

### 3.5 Attendance — history / absentees

**Screen:** `/attendance/history`  

| User does | API |
|-----------|-----|
| Select batch + date range / days back | `GET /t/{tid}/attendance/absentees?batch_id=&on_date=&days_back=` |

Purpose: teacher sees who to rebuke; independent of SMS.

---

### 3.6 Fees / payments

**Screen:** Fees this month (`/fees`)  
**Screen:** Nag list (`/fees/nag`)  

| Step | User does | System does | API |
|------|-----------|-------------|-----|
| 1 | Open Fees | Month grid per student | `GET /t/{tid}/payments` or `.../payments/batch/{batch_id}` |
| 2 | Mark paid + Lock | Locked immutable | `POST /t/{tid}/payments/mark-paid`, `POST .../lock` |
| 3 | Owner unlock | Audit | `POST .../unlock` |
| 4 | Waive (owner) | Status Waived; excluded from nag | mark waived with reason (service rule) |
| 5 | Nag list | Green = will message; white = skip | `GET .../payments/delayed/{batch_id}`, `POST .../notify-flag` |

**SPEC:** Locked payments excluded from naive last-write-wins sync; conflicts → owner log.

---

### 3.7 Exams

**Screen:** Exam entry (`/exams`)  
**Screen:** Analytics (`/exams/analytics`)  

| Step | User does | API (as wired) |
|------|-----------|----------------|
| Create / open exam | `POST/GET /t/{tid}/exams` |
| Enter scores | `POST /t/{tid}/exams/{id}/results` (when routed) |
| Summary | `GET /t/{tid}/exams/{id}/summary` |
| Heatmap / struggle heuristic | analytics routes when present |

**P1 bar:** Manual entry works offline-capable; history never lost on roll change.  
**Prediction:** transparent heuristic only (SPEC), not black-box ML in P1.

---

### 3.8 Settings

**Screens:** `/settings/staff`, `/settings/messaging`, `/settings/mode`  

| Sub | User does | API |
|-----|-----------|-----|
| Staff | Add staff, assign role | `GET/POST /t/{tid}/staff`, `GET/POST /t/{tid}/roles` / accounts |
| Messaging | Templates, channels, caps | `GET/PUT /t/{tid}/settings/messaging` |
| Mode | offline-first / cloud-first / hybrid | `GET/PUT /t/{tid}/settings/mode` |

**Nav:** Full primary nav + sub-tabs + Back to desk.  
**Mode change:** Guided migration, never silent (SPEC).

---

### 3.9 Desk daily happy path (UAT script)

1. Trial or sign-in → stay signed in after restart  
2. Create 1 batch  
3. Admit 2 students (sibling parent phones)  
4. Mark attendance for both  
5. Mark one fee paid + lock  
6. Open exam entry (smoke)  
7. Settings → Back to desk  
8. Airplane mode: open attendance, change still possible or clearly queued  

**Pass:** Zero terminal. Zero blank trap screens. Zero 404 on these calls.

---

## 4. Surface B — Teacher co-pilot (PHASE 2–3)

**Screens:** StyleProfile, OcrAssist, ReviewQueue, ItemBank, FlaggedThreads, CohortInsight  

| Intent | Typical API |
|--------|-------------|
| Style profile | `GET/PUT /t/{tid}/ai/style-profiles` |
| OCR assist | `POST /t/{tid}/ai/ocr` |
| Flagged threads | `GET /t/{tid}/ai/threads/flagged` |
| Recap draft | `POST /t/{tid}/ai/recap-draft` |
| Solve ask (related) | `POST /t/{tid}/solve/ask` |

**SPEC gates:** No ungrounded auto-publish; review queue; confidence flags; Bangla OCR “verify before grading”.  
**Status:** UI shells exist; full contract wiring is Phase 3 priority after desk P1 is solid.

---

## 5. Surface C — Student (PHASE 2)

**Join:** Staff admits student → join code (QR + alphanumeric, default 30-day expiry, rate limits).  
**Login:** OTP on configured identifier. Unlinked account = **zero data access**.

| Screen | Purpose | APIs (target) |
|--------|---------|----------------|
| StudentHome | Hub | home/summary when routed |
| StudentResults | Read-only results/attendance/fees | results + attendance read |
| StudentVault | Resources under rules | `GET /t/{tid}/vault` + access checks |
| StudentSolve | AI tutor | `POST /t/{tid}/solve/ask` |
| StudentThreads | Thread with teacher | threads list/messages when routed |

---

## 6. Surface D — Parent (PHASE 2)

| Step | Behavior | API |
|------|----------|-----|
| Link | Same join code → parent role on `admission_id` | `POST /t/{tid}/parents/link` |
| Portal | Read-only linked students only | parent view aggregation |
| Revoke | Owner revokes parent link, audit | staff/owner action |

---

## 7. Surface E — Founder console (PHASE 1.5–3)

**Auth:** Founder token / separate founder session — never expose token to centre UI or logs.

| Screen | User does | API |
|--------|-----------|-----|
| Dashboard | Tenant counts, trial/active/suspended, AI usage metrics only | `GET /founder/dashboard` |
| Tenants | List / open | `GET /founder/tenants`, `GET /founder/tenants/{id}` |
| Provision | Create tenant | provision flow |
| Activate / suspend / extend | Billing & cloud features only — **cannot wipe offline local DB** | `.../activate`, `.../suspend`, `.../extend` |
| Pricing | Tiers / quote | `GET /founder/pricing/tiers`, `.../quote` |
| Audit | Support actions | `GET /founder/audit` |

**Privacy:** No student PII in founder panel without time-boxed owner consent (SPEC).

---

## 8. Sync, offline, license

| Topic | Behavior |
|-------|----------|
| Offline core | Admission, attendance, payment lock, exam entry work without net |
| Sync | `POST /sync/push`, `POST /sync/pull` — idempotent, resumable |
| Conflicts | Field LWW; **locked payments** reject silent overwrite → conflict log |
| License | Periodic online check when online; delinquent → **read-only** lockout; data exportable, never deleted (SPEC §0) |

---

## 9. API contract conventions (client implementers)

1. Base URL: desktop `http://127.0.0.1:8741`; web may be same host or env `VITE_API_BASE`.  
2. `Authorization: Bearer <access_token>` on `/t/...` and protected routes.  
3. `credentials: include` for cookie refresh on web.  
4. On 401: try refresh once; if fail → login.  
5. On 429: show retry-after; do not tight-loop OTP.  
6. Error body: prefer `{ "detail": "..." }` for UI message.  
7. Tenant id: from JWT / `localStorage cohortos_tenant_id` after login — **never** ask centre staff to type raw UUIDs in normal flows.

---

## 10. Screen ↔ route map (frontend)

| Route | Screen component | Primary persona |
|-------|------------------|-----------------|
| `/login` | Login / Trial | All pre-auth |
| `/attendance` | TodayAttendance | Desk |
| `/attendance/history` | AttendanceHistory | Desk / teacher |
| `/admissions` | AdmissionsList | Desk |
| `/batches` | BatchSettings | Desk |
| `/fees` | FeesThisMonth | Desk |
| `/fees/nag` | GreenWhiteNagList | Desk |
| `/exams` | ExamEntry | Teacher / desk |
| `/exams/analytics` | ExamAnalytics | Teacher |
| `/vault` | VaultManagement | Teacher / owner |
| `/settings/staff` | StaffRoles | Owner |
| `/settings/messaging` | MessagingSettings | Owner |
| `/settings/mode` | ModeSettings | Owner |
| `/teacher/*` | Style, OCR, Review, ItemBank, Threads, Insight | Teacher |
| `/student/*` | Home, Solve, Results, Vault, Threads | Student |
| `/parent` | ParentPortal | Parent |
| `/founder/*` | Dashboard, Tenant, Provision, Pricing | Founder |

Router: **HashRouter** for Electron `file://` packaging (`#/attendance`).

---

## 11. Packaging & platforms (delivery)

| Platform | Target | Done means |
|----------|--------|------------|
| Linux | AppImage double-click | UI loads (relative assets), API bundled or local, stay signed in |
| Windows | Signed installer / portable | Same + SmartScreen-safe signing |
| Mac | Notarized DMG | Gatekeeper-safe |
| Web | Hosted static + API | HTTPS, CORS, PWA optional |
| Android | PWA first, Capacitor later | Not “responsive web only” as final claim |

---

## 12. Definition of done (production bar)

A phase is complete only if:

1. Every P1 flow in §3 passes the UAT script on a real machine.  
2. No primary nav trap; Back to desk / brand always works.  
3. OTP never requires terminal in pilot.  
4. Refresh survives process and OS restart.  
5. Batches/students persist on disk after restart.  
6. Automated tests cover SPEC `[BULLET]` payment lock, duplicate phone scope, cross-batch enrollment scope (expand until green).  
7. Network tab: zero unexpected 404 on P1 screens.  
8. Offline: core desk actions do not brick the UI.

---

## 13. Gap register (build next — order fixed)

### P1.5 — must close before calling desk “client-ready”

1. Wire any missing routes still called by Admissions/Batches/Fees/Exams (see legacy Group A list: migrate, batch detail, exam results, etc.).  
2. Empty states + CTAs on all desk lists.  
3. Stay-signed-in verified on Linux/Windows cold start.  
4. Settings never replaces primary nav.  
5. Linux AppImage + Windows portable signed path.  
6. Contract tests: one per P1 route, assert response shape UI uses.

### P2

Vault access-rules contract aligned; student join + parent link E2E; PWA.

### P3

AI review gate + grounded solve; founder consent access; multi-currency.

---

## 14. Open decisions (do not hardcode silently)

| # | Topic | Default until founder overrides |
|---|--------|----------------------------------|
| 1 | Annual discount % | Hold — finance sign-off |
| 2 | Android | PWA then Capacitor |
| 3 | Staff RBAC storage | Service-layer roles win over flat staff rows |
| 4 | Vault rules JSON shape | Match `ContentService` tested signature |
| 5 | SMS provider | Pilot on-screen OTP until Twilio/local gateway configured |
| 6 | Performance budgets | ≤3s desktop start target |

---

## 15. Working agreement for implementation sessions

1. Re-read SPEC_v3 § relevant modules + this PRD § for the flow being built.  
2. Implement **one lifecycle** end-to-end (UI → API → test) before the next.  
3. Prefer fixing §13 P1.5 gaps over new AI chrome.  
4. Never mark done without evidence: test run, or scripted click-through notes.  
5. Product name in UI: **CohortOS**.

---

## 16. Appendix — Minimal API cheat sheet (P1 desk)

```
POST /auth/centre-trial
POST /auth/request-otp
POST /auth/verify-otp          → access_token + refresh_token
POST /auth/refresh
POST /auth/logout
GET  /me
GET  /t/{tid}/batches
POST /t/{tid}/batches
GET  /t/{tid}/students
POST /t/{tid}/students
POST /t/{tid}/students/duplicate-check
GET  /t/{tid}/attendance...
POST /t/{tid}/attendance/manual
GET  /t/{tid}/payments...
POST /t/{tid}/payments/mark-paid | lock | unlock
GET  /t/{tid}/exams
GET/PUT /t/{tid}/settings/mode | messaging
GET/POST /t/{tid}/staff
```

---

*End of PRD v2.0. This document is the workflow contract for polishing CohortOS to production: screen → action → API → acceptance. SPEC_v3 remains the rules engine; where UI and SPEC conflict, SPEC wins and this PRD is updated explicitly.*
