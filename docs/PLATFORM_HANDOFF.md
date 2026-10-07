# Platform handoff (website / PWA / Android) — no feature work yet

## API surface
- OpenAPI at `/openapi.json` (route inventory test asserts ≥30 routes).
- Tenant-scoped resources under `/t/{tenant_id}/...`.
- Auth: centre-trial, request-otp, verify-otp, refresh; JWT bearer access + refresh rotation.

## Auth model
- Multi-tenant isolation: token must match `tenant_id`; cross-tenant reads return 401/403/404.
- Rate limits on OTP, refresh, and AI query (and auth middleware when test-expose is off).
- Production must not leave `COHORTOS_TEST_EXPOSE_OTP=1` or `COHORTOS_RATE_LIMIT_DISABLED=1`.

## What PWA/web may call
- All public auth routes + authenticated tenant APIs used by the desk app.
- Prefer same-origin or explicit CORS; no long-lived secrets in the client.

## Offline / sync assumptions
- Offline-first desk paths exist (SQLite per tenant); PWA should treat network as unreliable.
- Conflict resolution and queues are product rules already in the desk stack — new clients must not invent parallel ledgers.

## RAM tiers
- Verify sandbox: ~1.2GB (use `--low-mem`, single-threaded npm/playwright).
- Comfortable proof: 4GB+ (Docker.verify / laptop).

## Gates new clients must pass
1. Unit + skip-budget 0  
2. Route inventory (auth + isolation)  
3. Boot/backup hygiene  
4. Chaos / stress money paths when touching payments  
5. E2E smoke + axe on shipped UI  
6. No high npm/pip audit findings without written exception  
