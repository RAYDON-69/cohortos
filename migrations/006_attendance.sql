-- CoachMate Portion 3: Attendance / Irregularity (SPEC Module 2)
-- Devices, immutable punches, daily derived status, review flags.
-- Offline-first; tenant-scoped; supports biometric + manual + cross-batch.

PRAGMA foreign_keys = ON;

-- Registered biometric devices
CREATE TABLE IF NOT EXISTS attendance_devices (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    device_type TEXT NOT NULL DEFAULT 'zkteco',
    ip_address TEXT NOT NULL DEFAULT '',
    port INTEGER NOT NULL DEFAULT 4370,
    is_active INTEGER NOT NULL DEFAULT 1,
    last_seen_at TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attendance_devices_tenant ON attendance_devices(tenant_id);
CREATE INDEX IF NOT EXISTS idx_attendance_devices_active ON attendance_devices(tenant_id, is_active);

-- Immutable raw punches (biometric or manual)
CREATE TABLE IF NOT EXISTS punch_records (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT,
    device_user_id TEXT,
    device_id TEXT,
    punched_at TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('biometric', 'manual')),
    batch_id TEXT,
    origin_id TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_punches_tenant ON punch_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_punches_student_date ON punch_records(tenant_id, student_id, punched_at);
CREATE INDEX IF NOT EXISTS idx_punches_device_user ON punch_records(tenant_id, device_user_id);
CREATE INDEX IF NOT EXISTS idx_punches_device ON punch_records(tenant_id, device_id);

-- Derived daily attendance status (one row per student per calendar date)
CREATE TABLE IF NOT EXISTS attendance_records (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    date TEXT NOT NULL,                          -- YYYY-MM-DD
    status TEXT NOT NULL CHECK (status IN ('present', 'late', 'absent', 'cross_batch', 'review')),
    late_minutes INTEGER,
    credited_batch_id TEXT,
    source_precedence TEXT NOT NULL DEFAULT 'manual',
    punch_ids TEXT NOT NULL DEFAULT '[]',        -- JSON array
    flags TEXT NOT NULL DEFAULT '[]',            -- JSON array of flag types
    is_reviewed INTEGER NOT NULL DEFAULT 0,
    reviewed_at TEXT,
    reviewed_by TEXT,
    notes TEXT NOT NULL DEFAULT '',
    origin_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, student_id, date)
);

CREATE INDEX IF NOT EXISTS idx_attendance_tenant ON attendance_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_attendance_batch_date ON attendance_records(tenant_id, batch_id, date);
CREATE INDEX IF NOT EXISTS idx_attendance_student_date ON attendance_records(tenant_id, student_id, date);
CREATE INDEX IF NOT EXISTS idx_attendance_status ON attendance_records(tenant_id, status, date);

-- Human review queue (anti-proxy, bio/manual conflict)
CREATE TABLE IF NOT EXISTS review_flags (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    date TEXT NOT NULL,
    flag_type TEXT NOT NULL,
    attendance_record_id TEXT,
    punch_ids TEXT NOT NULL DEFAULT '[]',
    detail TEXT NOT NULL DEFAULT '',
    is_resolved INTEGER NOT NULL DEFAULT 0,
    resolved_at TEXT,
    resolved_by TEXT,
    resolution_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_review_flags_tenant ON review_flags(tenant_id);
CREATE INDEX IF NOT EXISTS idx_review_flags_open ON review_flags(tenant_id, is_resolved, date);
CREATE INDEX IF NOT EXISTS idx_review_flags_student ON review_flags(tenant_id, student_id, date);
