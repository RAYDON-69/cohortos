-- CoachMate Portion 4: Payment (SPEC Module 3)
-- Paid/unpaid per month, locking (one-way), green/white notify flag,
-- optional amount+receipt mode. Offline-first; tenant-scoped.

PRAGMA foreign_keys = ON;

-- Full payment records (supersedes stub in 005; CREATE IF NOT EXISTS is safe)
CREATE TABLE IF NOT EXISTS payment_records (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    batch_id TEXT NOT NULL DEFAULT '',
    roll TEXT NOT NULL DEFAULT '',
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    status TEXT NOT NULL DEFAULT 'unpaid' CHECK (status IN ('paid', 'unpaid')),
    locked INTEGER NOT NULL DEFAULT 0,
    locked_at TEXT,
    locked_by TEXT,
    unlocked_at TEXT,
    unlocked_by TEXT,
    amount REAL,                              -- NULL when amount mode off
    currency TEXT NOT NULL DEFAULT 'BDT',
    receipt_ref TEXT,
    notify_flag TEXT NOT NULL DEFAULT 'green' CHECK (notify_flag IN ('green', 'white')),
    notes TEXT NOT NULL DEFAULT '',
    origin_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, student_id, year, month)
);

CREATE INDEX IF NOT EXISTS idx_payment_records_tenant ON payment_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_payment_records_student ON payment_records(tenant_id, student_id);
CREATE INDEX IF NOT EXISTS idx_payment_records_batch_month ON payment_records(tenant_id, batch_id, year, month);
CREATE INDEX IF NOT EXISTS idx_payment_records_status ON payment_records(tenant_id, status, year, month);
CREATE INDEX IF NOT EXISTS idx_payment_records_locked ON payment_records(tenant_id, locked);

-- Owner unlock audit trail (also mirrored in main audit_log)
CREATE TABLE IF NOT EXISTS payment_unlock_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    payment_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    unlocked_by TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    previous_status TEXT NOT NULL DEFAULT 'paid',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_payment_unlock_tenant ON payment_unlock_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_payment_unlock_payment ON payment_unlock_events(payment_id);

-- Keep stub `payments` table in sync for Portion 2 migration path (HISTORY_TABLES)
-- Application writes primarily to payment_records; sync layer can mirror if needed.
