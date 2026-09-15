# PRD Addendum designs (GROK_FINAL_BUILD_PROMPT §1)

Source of truth order: SPEC_v3.md > prd.md + this addendum > judgment.
These sections use the same template as every other prd.md screen entry.

---

## A1. Sync Conflict Log (SPEC_v3 §7)

**Purpose:** Owner-only list of sync conflicts that must not auto-resolve via last-write-wins — especially locked-payment-record conflicts (SPEC §3, §7). Provides explicit resolve / keep-local / keep-remote actions with audit.

**Roles who can access:** Owner only. Desk/teacher/assistant redirected or permission-denied banner.

**Entry points:** Settings sub-nav “Conflicts”; deep link `/settings/conflicts`; badge on connectivity pill when conflict count > 0.

**Exit points:** deskNav / settings; after resolve stay on list.

**Data loaded on entry:**
- `GET /t/{tenant_id}/sync/conflicts` — **needs route** (service: sync_engine pending conflict store).
- Count badge: same endpoint or lightweight `GET .../sync/conflicts/count`.

**Actions available:**
| Control | Behaviour | API |
|--------|-----------|-----|
| List conflicts | Show table: entity, field, local value, remote value, reason (e.g. locked_payment), detected_at | GET conflicts |
| Keep local | Force local wins; audit | POST .../conflicts/{id}/resolve {choice: local} |
| Keep remote | Apply remote; audit | POST .../conflicts/{id}/resolve {choice: remote} |
| Mark reviewed | Soft dismiss non-blocking informational conflicts | POST .../conflicts/{id}/ack |

**Required UI states:**
- **Loading:** skeleton table rows.
- **Empty:** “No sync conflicts — all changes reconciled.” + link to Backup.
- **Error:** banner + Retry; never blank.
- **Offline:** list from local conflict store; resolve actions queue until online (or apply local immediately and mark pending ack).
- **Permission-denied:** non-owner sees banner “Only the centre owner can resolve sync conflicts” + Back.
- **Normal:** sorted by detected_at desc; locked-payment rows visually distinct (icon + Badge, not color alone).

**Edge cases:**
- Locked payment records never LWW — always appear here (SPEC §3, §7).
- Concurrent cell edits that are true conflicts (not per-field LWW) land here.
- Resolve is audit-logged.
- Empty conflict log must not look like an error.

**Current status:** Design complete; implementation Batch 2.

---

## A2. Backup & Data Export (SPEC_v3 §7)

**Purpose:** Owner-only disaster-recovery surface: trigger full dataset export (CSV or portable archive), view local snapshot schedule/status, confirm WAL mode is active. Offline-first centres on unreliable power need this — not optional polish.

**Roles who can access:** Owner only.

**Entry points:** Settings “Backup & export”; `/settings/backup`.

**Exit points:** Settings; deskNav.

**Data loaded on entry:**
- `GET /t/{tenant_id}/backup/status` — WAL flag, last snapshot time, schedule, disk path (local).
- Existing backup helpers in models/base `create_backup` / tests/test_backup.py.

**Actions available:**
| Control | Behaviour | API |
|--------|-----------|-----|
| Export CSV | Streaming zip of core tables (students, batches, attendance, payments, exams, results) | POST .../backup/export?format=csv |
| Export portable archive | SQLite snapshot + metadata | POST .../backup/export?format=archive |
| Snapshot now | Local file snapshot | POST .../backup/snapshot |
| Confirm WAL | Read-only indicator | status.wal_mode === 'wal' |

**Required UI states:**
- **Loading:** skeleton status card.
- **Empty:** N/A (status always present); if never snapshotted show “No snapshot yet — create one.”
- **Error:** visible + Retry; export failure does not wipe prior status.
- **Offline:** snapshot and local export work; cloud upload of archive queues.
- **Permission-denied:** non-owner banner.
- **Normal:** WAL badge (ok/warn), last snapshot, export buttons, schedule text.

**Edge cases:**
- Power-cut mid-export: partial file discarded; user can retry.
- Export is read-only on data; does not unlock payments.
- Large centres: progress indicator for export.

**Current status:** Design complete; implementation Batch 2.

---

## A3. License / Billing Lockout state (SPEC_v3 §0, v3.0 hardening)

**Purpose:** App-wide read-only lockout when rolling license check finds billing delinquent past grace window. Data remains visible and exportable; all write actions disabled with a clear billing message — not a blank screen or crash.

**Roles:** All authenticated staff experience lockout the same way for writes; owner sees additional “Renew / contact founder” CTA.

**Entry / trigger:** Background license check (existing SaaS models / founder billing). When `license.status === 'locked'` or grace expired → shell sets `billingLockout=true`.

**Exit:** Successful license refresh / payment clears lockout; logout still works.

**What every screen looks like in lockout:**
- Shell: persistent non-dismissible banner: “Billing past due — view and export only. Contact your centre owner or renew to restore edits.”
- All primary write controls (Admit, Mark paid, Lock, Manual attendance cycle, Create exam, Enter result, Create resource, Assign role, Save settings, Generate AI, etc.): **disabled** with tooltip/title “Unavailable while billing is locked.”
- Read paths (lists, history, analytics, vault metadata, exports): **enabled**.
- Backup & Export: **enabled** (disaster recovery must work).
- Conflict Log: view enabled; resolve disabled until unlock.
- Login / logout: unaffected.

**Required UI states (shell-level):**
- **Loading:** while license check in flight, do not flash lockout.
- **Empty:** N/A.
- **Error:** if license endpoint fails, degrade to last-known status; do not hard-lock on network blip without grace.
- **Offline:** use cached license decision; if cached locked, stay locked offline.
- **Permission-denied:** N/A (billing is not RBAC).
- **Normal (unlocked):** no banner.

**Edge cases:**
- Grace window still active → warning banner only, writes allowed.
- Founder super-admin path out of panel scope.

**Current status:** Design complete; implementation Batch 2 (context + shell banner + disable writes).

---

## B. Teacher screens — explicit six UI states

### CohortInsight
- **Loading:** skeleton cards for heatmap + struggle list.
- **Empty:** “No cohort data yet — complete an exam or select another batch.”
- **Error:** banner + Retry (failed heatmap/struggle/recap).
- **Offline:** cached aggregates if present; “Generate recap” disabled or queued with “will run when online / quota resets.”
- **Permission-denied:** desk/assistant hidden via nav; if deep-linked, banner.
- **Normal:** heatmap + struggle + recap draft CTA.

### ItemBank
- **Loading:** skeleton list.
- **Empty:** “No approved items yet — generate or wait for review.”
- **Error:** banner + Retry.
- **Offline:** browse cache; generate/push blocked or queued.
- **Permission-denied:** non-teacher/owner banner.
- **Normal:** filterable list, history, push to bank.

### StyleProfile
- **Loading:** skeleton form.
- **Empty:** “No style profile for this subject — add samples to lock tone.”
- **Error:** banner + Retry.
- **Offline:** read cache; save queues.
- **Permission-denied:** non-teacher/owner.
- **Normal:** subject selector + few-shot editor + save.

### FlaggedThreads
- **Loading:** skeleton queue.
- **Empty:** “No flagged threads — students are clear.”
- **Error:** banner + Retry.
- **Offline:** cached queue; take-over/reply blocked or queued.
- **Permission-denied:** non-teacher/owner.
- **Normal:** ranked list; open → take-over → reply.

### ReviewQueue
- **Loading:** skeleton cards.
- **Empty:** “Review queue clear — nothing pending approval.”
- **Error:** banner + Retry.
- **Offline:** cached items; approve/reject queue until online.
- **Permission-denied:** non-teacher/owner.
- **Normal:** approve / reject with reason; source chunks visible.

---

## C. Centre Setup Wizard (first-run)

**Purpose:** Bootstrap path when a centre has zero batches so a new client is not dropped into an empty Attendance grid with no way to populate it.

**Roles:** Owner (and desk if policy allows create). Shown only when `listBatches` returns empty after auth.

**Entry points:**
- After login/trial when batch count === 0 → redirect `/setup`.
- Cannot be reached once ≥1 batch exists (redirect to `/attendance`).

**Exit points:** “Finish” → `/attendance` with first batch selected; Cancel only if trial allows leaving (prefer no dead-end — Cancel → still stay on step 1 with message).

**Steps:**
1. **Centre confirm** — name display (from trial/provision); optional edit display name.
2. **First batch** — days, hour, display name → `POST /batches`.
3. **First admission** — name, phone, roll preview → `POST /students`.
4. **Done** — summary + “Go to Attendance.”

**Data / Actions:** existing batch + student APIs only.

**Required UI states:**
- **Loading:** per-step submit disabled + skeleton.
- **Empty:** N/A (wizard is the empty-state replacement).
- **Error:** inline field errors + step-level Retry.
- **Offline:** step 2–3 queue creates if offline-first; show queued badge; block finish until local ids exist.
- **Permission-denied:** non-owner without create rights.
- **Normal:** linear stepper; Back between steps 2–3.

**Edge cases:**
- User refreshes mid-wizard: re-enter at first missing step (no batch → step 2; batch but no students → step 3).
- Duplicate phone on first admit: same duplicate-check as AdmissionsList.

**Current status:** Design complete; implementation Batch 4.
