# Requirements ↔ Tests traceability (P35)

| Req ID | Module | Requirement (summary) | Test ID(s) | Status |
|--------|--------|----------------------|------------|--------|
| R-AUTH-01 | Auth | Staff OTP login + session | e2e/smoke.spec.ts | TESTED |
| R-AUTH-02 | Auth | Bearer required on tenant routes | tests/test_auth_matrix.py | TESTED |
| R-AUTH-03 | Auth | Cross-tenant isolation | tests/test_auth_matrix.py | TESTED |
| R-ADM-01 | Admission | Admit student | e2e CORE | TESTED |
| R-ATT-01 | Attendance | Mark Present/Late/Absent | e2e CORE | TESTED |
| R-FEE-01 | Payment | Record fee payment | e2e CORE | TESTED |
| R-FEE-02 | Payment | Partial payment never negative | tests/test_fee_properties.py | TESTED |
| R-FEE-03 | Payment | Idempotent payment replay | tests/test_fee_properties.py | TESTED |
| R-FEE-04 | Payment | BDT 2-decimal rounding | tests/test_fee_properties.py | TESTED |
| R-FEE-08 | Payment | Refund path | — | UNTESTED |
| R-MSG-01 | Messaging | Parent notice | — | UNTESTED |
| R-RPT-01 | Reports | Attendance report export | — | UNTESTED |
| R-LOC-01 | Locale | Asia/Dhaka no DST | tests/test_locale_bd.py | TESTED |
| R-LOC-02 | Locale | BD phone formats | tests/test_locale_bd.py | TESTED |
| R-OFF-01 | Offline | Save while API down queues | tests/test_offline_unreliable.py | TESTED |
| R-SUB-01 | SaaS | Trial fields | tests/test_subscription_licensing.py | TESTED |
| R-SUB-02 | SaaS | Lapsed read-only | — | NOT-DONE |
| R-SUB-03 | SaaS | Licence token tamper | — | NOT-DONE |
| R-DIAG-01 | Support | Diagnostics export | tests/test_diagnostics_api.py + UI | TESTED |
| R-MIG-01 | Ops | Migration replay 3 states | tests/test_migration_replay.py | TESTED |
| R-SEC-FUZZ | Security | Fuzz no 5xx | security-fuzz CI | TESTED |
| R-SEC-NPM | Security | npm prod high=0 | security-licenses CI | TESTED |

Top untested by impact: R-FEE-08 refunds, R-MSG-01 parent notices, R-RPT-01 reports, R-SUB-02 lapsed mode.
