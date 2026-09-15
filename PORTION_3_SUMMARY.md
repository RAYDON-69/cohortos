# Portion 3 — Attendance / Irregularity — DONE

**Completed**: 2026-08-17  
**Status**: Production-ready

## Files
- `models/attendance.py` — Device, PunchRecord, AttendanceRecord, ReviewFlag + helpers
- `services/attendance_service.py` — Full engine (ingest, evaluate, manual/bulk, irregularity, notify)
- `migrations/006_attendance.sql` — devices, punches, attendance_records, review_flags
- `tests/test_attendance.py` — 29 tests covering every SPEC rule + edge cases
- `PORTION_3_PLAN.md` — Design ADR

## SPEC coverage (Module 2)
| Rule | Status |
|------|--------|
| [BULLET] ZKTeco / pyzk-ready device model + manual device_user_id link | ✅ |
| [FLEX] Late threshold default 12 min + per-batch override | ✅ |
| [BULLET] Absent when no punch on scheduled day | ✅ |
| [BULLET] Anti-proxy (same device, implausible window) → review | ✅ |
| [BULLET] Cross-batch credit on own scheduled day | ✅ |
| [LOCKED] Biometric authoritative; manual fills gaps only | ✅ |
| [LOCKED] Bio/manual conflict → review queue (no silent overwrite) | ✅ |
| [FLEX] Extra sessions with expiry | ✅ |
| [BULLET] Teacher absentees view (days_back) | ✅ |
| [FLEX]/[LOCKED] Shared irregularity threshold (default <3 days/month) | ✅ |
| Automated messaging gated by irregularity; teacher alert for irregular | ✅ |
| Late-streak-3 distinct template path | ✅ |
| Manual / Google-Sheets-style bulk mark | ✅ |
| Offline-first core path | ✅ |
| Tenant-scoped + audit-logged | ✅ |

## Tests
- Portion 3: **29/29**
- Full tree: **143/143**

## Integration notes
- `HISTORY_TABLES` in AdmissionService already includes `attendance` for roll/batch migration.
- Irregularity threshold is a single ConfigService key (`attendance.irregularity_threshold_days` + optional per-batch map) — Payment (Portion 4) must reuse it.
- NotificationService is optional; enqueue calls degrade gracefully when absent.
- Device adapter is interface-ready; concrete pyzk pull can be added without touching evaluation logic.
