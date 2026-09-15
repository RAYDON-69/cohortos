# Portion 3 — Attendance / Irregularity (SPEC Module 2)

**Status**: In progress  
**Goal**: Production-ready, offline-first, multi-tenant attendance engine that fully implements every [LOCKED]/[BULLET]/[FLEX] rule in SPEC §2 and feeds the shared irregularity threshold used by Payment (Module 3).

## Design Decisions

### 1. Data model (two layers)

**Raw layer (immutable punches)**  
- `punch_records`: every biometric or manual event. Never deleted or silently mutated.  
  Fields: id, tenant_id, student_id (nullable until linked), device_user_id, device_id,  
  punched_at (ISO), source (`biometric` | `manual`), batch_id (optional context),  
  origin_id (device/client), created_at, metadata (JSON).

**Derived layer (daily status)**  
- `attendance_records`: one row per (student_id, date). Status is recomputed from punches  
  when new punches arrive or on demand.  
  status ∈ {`present`, `late`, `absent`, `cross_batch`, `review`}  
  Also stores: late_minutes, credited_batch_id, source_precedence, flags[], reviewed_at,  
  reviewed_by, notes.

**Supporting**  
- `attendance_devices`: IP/port/type/name + last_seen.  
- `review_flags`: anti-proxy or bio/manual conflict cases requiring human decision.  
- Config keys (via ConfigService):  
  - `attendance.late_threshold_minutes` (default 12)  
  - `attendance.late_threshold_per_batch` (dict batch_id → minutes)  
  - `attendance.anti_proxy_window_seconds` (default 90)  
  - `attendance.irregularity_threshold_days` (default 3) — **shared with Payment**  
  - `attendance.messaging_time` / per-batch  
  - templates: absence, late, late_streak_3

### 2. Evaluation order (exactly as [LOCKED])

1. Collect **all** punches (biometric + manual) for the student on that calendar date.  
2. Run anti-proxy across the whole set (same device_id + Δt < window → flag).  
3. From surviving punches determine:  
   - Does any punch fall inside the student’s own batch window (start → start+threshold)? → present / late  
   - Does any punch fall inside another batch’s window **on a day that is a scheduled day for the student’s own batch** (or active extra_session)? → cross_batch credit  
4. Biometric punches are authoritative: a manual mark never overwrites an existing biometric-derived status.  
5. If biometric-derived status and a later manual mark disagree, create a `review_flag` instead of auto-resolving.

### 3. Cross-batch rule

A student is credited Present/Cross-batch for day D if:  
- They have a valid punch on D, **and**  
- D is one of their batch’s scheduled days (or an active extra_session day), **and**  
- The punch time matches any batch (own or other) that runs on that weekday.

### 4. Manual attendance (Google-Sheets style)

- Single mark: `mark_manual(student_id, date, status|time, actor)`  
- Bulk: `bulk_mark(batch_id, date, {student_id: status|time, ...})` — transactional, audit one entry + per-student.  
- Manual only fills gaps; never clobber biometric.

### 5. Device integration

- Abstract `BiometricDeviceAdapter` with `pull_punches(since)` method.  
- Concrete `ZKTecoAdapter` (uses `pyzk` if installed, otherwise raises clear ImportError with fallback path).  
- Manual linking: `link_device_user(student_id, device_user_id)`.  
- Ingest path is the same whether punches come from adapter or manual entry.

### 6. Teacher daily view & messaging

- `get_absentees(batch_id, date, days_back=1)` → list of students with status=absent.  
- After daily close (or on demand), `evaluate_and_notify(batch_id, date)`:  
  - Skip students below irregularity threshold.  
  - For those, queue absence / late / late-streak messages via existing NotificationService.  
  - For irregular students, emit consolidated teacher alert (attendance + payment status placeholder).

### 7. Offline / sync

- Every write goes through DataAccessLayer first (local).  
- Punches and attendance_records carry origin_id + updated_at for LWW field-level merge (Portion 1).  
- History tables already include `attendance` for roll/batch migration (Portion 2).

### 8. Build order

1. models/attendance.py + migration 006  
2. services/attendance_service.py (core evaluation + manual + bulk)  
3. Device adapter stub + link API  
4. Irregularity helpers + NotificationService integration  
5. Comprehensive tests (happy path + every edge in SPEC)  
6. Full suite regression + edge-case hardening  
7. Summary + BUILD_PLAN update  

## Non-goals for this portion
- Actual network pull from a real ZKTeco unit (adapter interface + mock is enough; pyzk is optional runtime dep).  
- Payment locking / green-white box (Portion 4).  
- UI.  

## Success criteria
- All SPEC §2 rules implemented and tested.  
- 100 % of new tests pass; existing 114 tests remain green.  
- Offline-first: no network required for mark / evaluate / absentee list.  
- Shared irregularity threshold is a single config key.  
- Review queue for conflicts; no silent overwrites.  
"""
