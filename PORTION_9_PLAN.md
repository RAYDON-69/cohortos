# Portion 9 — Student & Parent Accounts (SPEC Module 8)

**Confirmed decisions (user 2026-08-17):**
1. Full Module 8 domain implementation — SPEC [LOCKED], no pause.
2. OTP via NotificationService + mock channel for tests.
3. Parent↔student links within one centre; cross-centre deferred to M10/11.
4. Teacher takeover on AI threads + priority ranking of flagged threads.
5. Continue from p8 → CohortOS_portions_0-9_production.zip.

## Acceptance criteria

- [ ] CohortOSAccount model (phone/email identifiers, dedup)
- [ ] Signup creates unlinked account (zero access until link)
- [ ] link(admission_id, account_id) via join code OR staff manual — audit logged
- [ ] Regenerate join code invalidates prior; single-use; expiry
- [ ] Unlink / reassign by owner
- [ ] Passwordless OTP login via NotificationService (mock in tests)
- [ ] Parent account + parent_student_links (same centre)
- [ ] Student read surface: attendance/payment/results gated on linked account
- [ ] Teacher takeover messages on AI threads; flagged-thread priority queue
- [ ] Wired into CohortOSApp
- [ ] Migration 011_accounts.sql
- [ ] tests/test_accounts.py — happy path + edge cases
- [ ] Full tree green + zip 0–9
