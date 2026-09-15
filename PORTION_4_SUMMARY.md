# Portion 4 — Payment — DONE

**Completed**: 2026-08-17  
**Status**: Production-ready

## Files
- `models/payment.py` — PaymentRecord, PaymentUnlockEvent, green/white flags
- `services/payment_service.py` — lock/unlock, notify flags, delayed messaging, amount mode
- `migrations/007_payments.sql` — payment_records + unlock events
- `tests/test_payment.py` — 29 tests

## SPEC coverage (Module 3)
| Rule | Status |
|------|--------|
| [FLEX] Default paid/unpaid per month (no amount) | ✅ |
| [FLEX] Optional amount + receipt mode | ✅ |
| [BULLET] Lock marks paid + immutable; manual only | ✅ |
| [BULLET] Owner unlock with audit + unlock event | ✅ |
| [BULLET] Green/white box; white persists (no auto-reset) | ✅ |
| [LOCKED] Irregularity exclusion reuses Attendance threshold | ✅ |
| [NEW] bKash/Nagad deep-link in reminder context | ✅ |
| Teacher delayed-payment summary (opt-in) | ✅ |
| Offline-first, tenant-scoped, audit-logged | ✅ |
| HISTORY_TABLES `payments` stub mirrored for migration | ✅ |

## Tests
- Portion 4: **29/29**
- Full tree: **172/172**

## Integration
- Inject `AttendanceService` for `is_irregular()` — single shared threshold.
- NotificationService optional; enqueue degrades offline.
- Lock is one-way; sync must never unlock from an older write (Portion 1 LWW + payment lock exception already documented).
