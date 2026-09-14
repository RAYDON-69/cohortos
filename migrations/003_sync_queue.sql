-- CoachMate Portion 1.1: Sync Queue Schema
-- SQLite schema for offline-first sync engine with durable storage

-- Enable SQLite extensions
PRAGMA foreign_keys = ON;

-- Sync queue table for pending operations
CREATE TABLE sync_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type TEXT NOT NULL CHECK (operation_type IN ('create', 'update', 'delete')),
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    old_state JSON, -- Full state before mutation (null for creates)
    new_state JSON NOT NULL, -- Full state after mutation
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sync_status TEXT NOT NULL DEFAULT 'pending' CHECK (sync_status IN ('pending', 'in_progress', 'completed', 'failed')),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    last_attempt_time TEXT,
    record_hash TEXT -- Hash for conflict detection
    -- NOTE: No UNIQUE(record_id, table_name, tenant_id). Concurrent ops on the
    -- same record must coexist so field-level conflict detection can see them.
    -- Last-write-wins is applied at resolve/apply time.
);


-- Sync conflict log table
CREATE TABLE sync_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    local_value JSON,
    remote_value JSON,
    resolved_by TEXT NOT NULL DEFAULT 'local', -- 'local'=unresolved marker, 'remote'/'manual'=resolved
    resolved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    operation_type TEXT NOT NULL CHECK (operation_type IN ('create', 'update', 'delete')),
    error_message TEXT,
    UNIQUE(record_id, table_name, tenant_id, field_name)
);

-- Sync session tracking
CREATE TABLE sync_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    start_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time TEXT,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    records_synced INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    sync_mode TEXT NOT NULL CHECK (sync_mode IN ('offline-first', 'cloud-first', 'hybrid')),
    last_operation_id INTEGER,
    FOREIGN KEY (last_operation_id) REFERENCES sync_queue(id)
);

-- Sync status tracking per tenant
CREATE TABLE tenant_sync_status (
    tenant_id TEXT PRIMARY KEY,
    last_sync_time TEXT,
    sync_enabled BOOLEAN DEFAULT TRUE,
    conflict_resolution_strategy TEXT DEFAULT 'last-write-wins' CHECK (conflict_resolution_strategy IN ('last-write-wins', 'manual', 'merge')),
    offline_changes INTEGER DEFAULT 0,
    pending_operations INTEGER DEFAULT 0,
    last_error TEXT,
    error_count INTEGER DEFAULT 0,
    settings JSON DEFAULT '{}'
);

-- Indexes for performance
CREATE INDEX idx_sync_queue_tenant ON sync_queue(tenant_id);
CREATE INDEX idx_sync_queue_status ON sync_queue(sync_status);
CREATE INDEX idx_sync_queue_created_at ON sync_queue(created_at);
CREATE INDEX idx_sync_conflicts_tenant ON sync_conflicts(tenant_id);
CREATE INDEX idx_sync_conflicts_resolved ON sync_conflicts(resolved_at);
CREATE INDEX idx_sync_sessions_tenant ON sync_sessions(tenant_id);
CREATE INDEX idx_sync_sessions_status ON sync_sessions(status);

-- View for active sync queue
CREATE VIEW active_sync_queue AS
SELECT * FROM sync_queue
WHERE sync_status = 'pending'
ORDER BY created_at ASC;