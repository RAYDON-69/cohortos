# CohortOS threat model (one page)

## Assets
- Tenant student/parent PII, fees, attendance, vault files, JWT secrets, LLM API keys, backups.

## Trust boundaries
1. Browser/desk UI ↔ local FastAPI  
2. Local API ↔ SQLite / vault disk  
3. Optional cloud sync / LLM providers (opt-in)  
4. Jitsi / broadcast URLs (external media)  
5. CI / supply chain

## Top 10 attack scenarios → coverage

| # | Scenario | Control / test | Status |
|---|----------|----------------|--------|
| 1 | Stolen desk session token | short-lived JWT, refresh; auth matrix | UNVERIFIED in CI |
| 2 | Cross-tenant IDOR | `_require_tenant` + `test_cross_tenant_idor_blocked` | PROVEN unit path |
| 3 | OTP brute force | rate limiter + Retry-After; prod unit test | PROVEN unit |
| 4 | SSRF via broadcast/recording URL | HTTPS + host allow-list tests | PROVEN unit |
| 5 | Path traversal vault/backup | backup checksum; path tests | PARTIAL |
| 6 | Zip-slip restore | restore from JSON not zip today | N/A / monitor |
| 7 | Prompt injection → tool call | agent safety + confirm | UNVERIFIED |
| 8 | Dependency RCE (npm/pip) | audit gates, SBOM, allowlists | PARTIAL |
| 9 | Malicious demo seed mix-in | DEMO_COHORTOS marker + remove | PROVEN unit |
| 10 | Local model resource exhaustion | RAM gating | PROVEN unit |

Live media, CodeQL repo setting, and full matrix over every route remain **UNVERIFIED** until CI executes them on main.

## P35 coverage map
| Scenario | Test |
|----------|------|
| Cross-tenant IDOR | auth-matrix CI |
| API 5xx via fuzz | schemathesis v4 CI |
| OTP brute force | rate-limit probe |
| npm HIGH in prod | npm_audit_gate --omit=dev |
| Chroma server RCE | embedded-only + allowlist canary |
| Payment negative balance | test_fee_properties |
| Offline data loss | test_offline_unreliable |
