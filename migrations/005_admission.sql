-- CoachMate Portion 2: Admission, Batches, Join Codes, Migration Logs
-- Aligns with SPEC Module 1 [LOCKED] roll encoding and Module 8 join codes.

PRAGMA foreign_keys = ON;

-- Batches
CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    days TEXT NOT NULL DEFAULT '[]',          -- JSON array of day keys
    hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
    day_bitmask INTEGER NOT NULL DEFAULT 0 CHECK (day_bitmask >= 0 AND day_bitmask <= 127),
    name_override INTEGER NOT NULL DEFAULT 0, -- boolean
    template_id TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    extra_sessions TEXT NOT NULL DEFAULT '[]', -- JSON
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_batches_tenant ON batches(tenant_id);
CREATE INDEX IF NOT EXISTS idx_batches_active ON batches(tenant_id, is_active);

-- Batch templates
CREATE TABLE IF NOT EXISTS batch_templates (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    coaching_type TEXT NOT NULL DEFAULT 'hsc',
    default_days TEXT NOT NULL DEFAULT '[]',
    default_hour INTEGER NOT NULL DEFAULT 14,
    exam_structure TEXT NOT NULL DEFAULT '{}',
    messaging_templates TEXT NOT NULL DEFAULT '{}',
    has_ai_prompt INTEGER NOT NULL DEFAULT 0,
    ai_prompt_request_id TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_batch_templates_tenant ON batch_templates(tenant_id);

-- Students / admissions (id = admission_id)
CREATE TABLE IF NOT EXISTS students (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    roll TEXT NOT NULL,
    student_phone TEXT DEFAULT '',
    parent_phones TEXT NOT NULL DEFAULT '[]',  -- JSON array
    whatsapp TEXT DEFAULT '',
    coachmate_account_id TEXT,                 -- linked via join code or staff
    custom_fields TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 1,
    biometric_device_user_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_students_tenant ON students(tenant_id);
CREATE INDEX IF NOT EXISTS idx_students_batch ON students(tenant_id, batch_id);
CREATE INDEX IF NOT EXISTS idx_students_roll ON students(tenant_id, roll);
CREATE INDEX IF NOT EXISTS idx_students_phone ON students(tenant_id, student_phone);

-- Per-admission join codes (Module 8 primary)
CREATE TABLE IF NOT EXISTS join_codes (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    admission_id TEXT NOT NULL,
    code TEXT NOT NULL,
    is_used INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    used_by_account_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_join_codes_tenant ON join_codes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_join_codes_admission ON join_codes(admission_id);
CREATE INDEX IF NOT EXISTS idx_join_codes_code ON join_codes(tenant_id, code);

-- Migration audit log (atomic roll/batch changes)
CREATE TABLE IF NOT EXISTS migration_logs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    old_roll TEXT NOT NULL,
    new_roll TEXT NOT NULL,
    old_batch_id TEXT NOT NULL,
    new_batch_id TEXT NOT NULL,
    tables_migrated TEXT NOT NULL DEFAULT '[]',
    records_moved INTEGER NOT NULL DEFAULT 0,
    actor_id TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    error_message TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_migration_logs_tenant ON migration_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_migration_logs_student ON migration_logs(student_id);

-- History tables (stubs for migration targets; full schemas arrive in later portions)
CREATE TABLE IF NOT EXISTS attendance (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    roll TEXT,
    batch_id TEXT,
    date TEXT,
    status TEXT,
    source TEXT,              -- biometric | manual
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    roll TEXT,
    batch_id TEXT,
    month TEXT,
    status TEXT,              -- paid | unpaid
    locked INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS exam_results (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    roll TEXT,
    batch_id TEXT,
    exam_name TEXT,
    score REAL,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    roll TEXT,
    batch_id TEXT,
    topic TEXT,
    created_at TEXT,
    updated_at TEXT
);
