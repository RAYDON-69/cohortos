# Portion 10 — Multi-Tenancy SaaS + Founder Super-Admin (SPEC Module 10)

## Scope

1. **Tenant registry** — provision, suspend, extend, status lifecycle (active/trial/suspended)
2. **Tenant isolation hardening** — explicit cross-tenant denial tests; founder is sole exception via audited path
3. **Pricing engine** — Starter ≤500 @ ৳5k, Growth ≤1500 @ ৳12k default, Scale ≤6000 custom; overage; annual discount
4. **BYOK** — per-tenant Gemini key storage (never logged)
5. **Founder super-admin** — list tenants, usage metrics (query volume, 429 rate, cache hit, MCQ/written split — NO Gemini spend), suspend/extend, billing status
6. **AI usage metrics collector** — aggregates from existing AI quota/cache/solve paths

## Out of scope

- Real payment gateway / Stripe
- Module 11 cross-centre parent portal
- UI

## Acceptance

- Pricing calc correctness for all tiers + overage + annual
- Cross-tenant isolation tests pass
- Founder can list/suspend/extend; cannot be impersonated by centre owner
- Metrics present without any spend visibility
- Full tree green + zip 0–10
