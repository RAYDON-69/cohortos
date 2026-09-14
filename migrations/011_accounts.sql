-- CoachMate Portion 9: Student & Parent Accounts (SPEC Module 8)
-- Offline-first; tenant-scoped.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS coachmate_accounts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student',
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    primary_admission_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_accounts_tenant ON coachmate_accounts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_accounts_phone ON coachmate_accounts(tenant_id, phone);
CREATE INDEX IF NOT EXISTS idx_accounts_email ON coachmate_accounts(tenant_id, email);

CREATE TABLE IF NOT EXISTS parent_student_links (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    parent_account_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    linked_by TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_parent_links ON parent_student_links(tenant_id, parent_account_id);

CREATE TABLE IF NOT EXISTS login_otps (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'sms',
    destination TEXT NOT NULL DEFAULT '',
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    is_used INTEGER NOT NULL DEFAULT 0,
    used_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_otps_account ON login_otps(tenant_id, account_id);

CREATE TABLE IF NOT EXISTS account_sessions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    token TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON account_sessions(token);
