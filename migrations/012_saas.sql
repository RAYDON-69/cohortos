-- CoachMate Portion 10: SaaS multi-tenancy + founder control plane (SPEC Module 10)

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS saas_tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'trial',
    tier TEXT NOT NULL DEFAULT 'starter',
    mode TEXT NOT NULL DEFAULT 'offline-first',
    owner_email TEXT NOT NULL DEFAULT '',
    owner_phone TEXT NOT NULL DEFAULT '',
    student_count INTEGER NOT NULL DEFAULT 0,
    monthly_price_bdt REAL NOT NULL DEFAULT 5000,
    overage_rate_bdt REAL NOT NULL DEFAULT 15,
    annual_discount REAL NOT NULL DEFAULT 0.15,
    billing_cycle TEXT NOT NULL DEFAULT 'monthly',
    trial_ends_at TEXT,
    suspended_at TEXT,
    suspended_reason TEXT NOT NULL DEFAULT '',
    extended_until TEXT,
    gemini_key_present INTEGER NOT NULL DEFAULT 0,
    gemini_key_fingerprint TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saas_status ON saas_tenants(status);
CREATE INDEX IF NOT EXISTS idx_saas_code ON saas_tenants(code);

CREATE TABLE IF NOT EXISTS tenant_ai_metrics (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    centre_tenant_id TEXT NOT NULL DEFAULT '',
    period TEXT NOT NULL,
    query_volume INTEGER NOT NULL DEFAULT 0,
    mcq_count INTEGER NOT NULL DEFAULT 0,
    written_count INTEGER NOT NULL DEFAULT 0,
    rate_limit_hits INTEGER NOT NULL DEFAULT 0,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    cache_misses INTEGER NOT NULL DEFAULT 0,
    offline_degrades INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE (centre_tenant_id, period)
);
CREATE INDEX IF NOT EXISTS idx_metrics_tenant ON tenant_ai_metrics(tenant_id, period);

CREATE TABLE IF NOT EXISTS founder_audit (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT '',
    actor_id TEXT NOT NULL DEFAULT 'founder',
    detail TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_founder_audit_time ON founder_audit(created_at);
