# Portion 9 — Student & Parent Accounts (Module 8) — DONE

**Completed**: 2026-08-17  
**Status**: Production-ready

## Deliverables

| File | Role |
|------|------|
| `models/accounts.py` | CohortOSAccount, ParentStudentLink, LoginOTP, AccountSession |
| `services/account_service.py` | Signup, link/unlink, OTP login, parent links, teacher takeover, priority queue |
| `migrations/011_accounts.sql` | Schema |
| `tests/test_accounts.py` | 19 tests |
| `services/app.py` | `app.accounts` wired |

## SPEC coverage (Module 8 [LOCKED])

| Rule | Status |
|------|--------|
| link(admission_id, account_id) single operation | ✅ |
| Per-admission join code primary path | ✅ (via AdmissionService) |
| Staff manual link fallback + confirm name | ✅ |
| Join code single-use; regenerate invalidates prior | ✅ |
| Unlinked account = zero access | ✅ |
| No upfront email/SMS verification at signup | ✅ |
| Passwordless OTP via NotificationService | ✅ |
| Account identifier phone/email/both [FLEX] | ✅ |
| Dedup on identifiers | ✅ |
| Owner unlink/reassign; audit logged | ✅ |
| Parent↔student links (same centre) | ✅ |
| Student read view (attendance/payments/results/threads) | ✅ |
| Teacher takeover on AI threads | ✅ |
| Flagged thread priority queue (confidence-based) | ✅ |

## Tests

- Portion 9: **19/19**
- Full tree: **279/279**
