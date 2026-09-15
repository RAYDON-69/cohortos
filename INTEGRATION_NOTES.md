# CohortOS Integrated Build v1.2 — Guidance

## Included in this build

### Issues 1–5 (closed)
1. **Real OTP login** — LoginPlaceholder → `/auth/request-otp` + `/auth/verify-otp`
2. **API surface** — thin routes wrapping tested service methods (signatures match)
3. **Founder token** — `COHORTOS_FOUNDER_TOKEN` required; no silent default; startup refuses if missing
4. **Refresh token storage**
   - Web: httpOnly cookie `cohortos_refresh` (path `/auth`); access token **memory only**
   - Electron: `safeStorage` via preload IPC; access token **memory only**
5. **E2E** — Playwright specs under `frontend/e2e/`

### Deferred features now present (optional / env-gated)
| Feature | How to enable | Default |
|---|---|---|
| **Gemini SDK** | `pip install google-generativeai` + `GEMINI_API_KEY` | MockLLMProvider; OfflineError if key/SDK missing |
| **Payment gateway** | Config deep-links or `COHORTOS_PAYMENT_WEBHOOK_SECRET` | DeepLinkGateway (bKash/Nagad) |
| **Parent cross-tenant** | `COHORTOS_ALLOW_CROSS_TENANT_PARENT=1` + owner role | **Blocked** (same-tenant only) |
| **Biometric driver** | `pip install pyzk` + device IP | Routes return 501 if pyzk absent; pull endpoint ready |

## Required environment

```bash
export COHORTOS_JWT_SECRET='long-random-secret-32+'
export COHORTOS_FOUNDER_TOKEN='long-random-founder-token'
export COHORTOS_AUTH_DB=/var/lib/cohortos/auth.db   # not :memory:
export COHORTOS_CLOUD_DB=/var/lib/cohortos/cloud.db  # not :memory:
# optional
export GEMINI_API_KEY=...
export COHORTOS_COOKIE_SECURE=true
export COHORTOS_CORS_ORIGINS=https://app.example.com
export COHORTOS_ALLOW_CROSS_TENANT_PARENT=0
export COHORTOS_PAYMENT_WEBHOOK_SECRET=...
```

## Start

```bash
cd CohortOS
pip install -r requirements.txt
# optional: pip install google-generativeai pyzk
uvicorn api.main:create_api_app_or_raise --factory --host 0.0.0.0 --port 8000

cd frontend && npm install && npm run dev
```

## Bulletproof verification performed (independent scripts, not just project tests)

| Check | Result |
|---|---|
| Founder token missing → refuse start | PASS |
| Founder wrong token → 403 | PASS |
| Founder dashboard / tiers / quote / provision | PASS |
| Health 200 | PASS |
| Unauthenticated tenant route → 401/403 | PASS |
| Authenticated students list | PASS |
| Cross-tenant API access blocked | PASS |
| Cross-tenant parent link blocked by default | PASS |
| Refresh rotation + Set-Cookie | PASS |
| Payment intent (deeplink gateway) | PASS |
| Biometric status (pyzk flag) | PASS |
| Gemini no-key → OfflineError (not crash) | PASS |
| No `founder-dev-token` in prod paths | PASS |
| TokenService methods match routes (`issue_access` / `rotate_refresh`) | PASS |

## Not fully verified in this environment
- Live Playwright against seeded OTP account
- Real ZKTeco hardware / real Gemini network calls
- Electron safeStorage on a desktop OS
- Full pytest suite re-run after every route change (smoke + signature alignment done)
