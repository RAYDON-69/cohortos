-- CoachMate Portion 6: Content / Vault (SPEC Module 5)
-- Resources, access rules, anti-leak, offline cache, live sessions, viewer tokens.
-- Offline-first; tenant-scoped.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS content_resources (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    resource_type TEXT NOT NULL
        CHECK (resource_type IN (
            'pdf', 'sheet', 'video_youtube', 'video_mp4',
            'image', 'live_recording', 'link'
        )),
    topic TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    batch_ids TEXT NOT NULL DEFAULT '[]',           -- JSON array
    url TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '',
    youtube_timestamps TEXT NOT NULL DEFAULT '[]',  -- JSON
    mime_type TEXT NOT NULL DEFAULT '',
    file_size_bytes INTEGER NOT NULL DEFAULT 0,
    total_chunks INTEGER NOT NULL DEFAULT 0,
    uploaded_chunks INTEGER NOT NULL DEFAULT 0,
    checksum TEXT NOT NULL DEFAULT '',
    access_rules TEXT NOT NULL DEFAULT '{}',        -- JSON AccessRuleset
    protection_level TEXT NOT NULL DEFAULT 'owner_only'
        CHECK (protection_level IN ('owner_only', 'relaxed', 'open')),
    watermark INTEGER NOT NULL DEFAULT 1,
    no_download INTEGER NOT NULL DEFAULT 1,
    session_token_required INTEGER NOT NULL DEFAULT 1,
    protection_relaxed_by TEXT,
    protection_relaxed_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT,
    origin_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_content_resources_tenant ON content_resources(tenant_id);
CREATE INDEX IF NOT EXISTS idx_content_resources_topic ON content_resources(tenant_id, topic);
CREATE INDEX IF NOT EXISTS idx_content_resources_type ON content_resources(tenant_id, resource_type);
CREATE INDEX IF NOT EXISTS idx_content_resources_active ON content_resources(tenant_id, is_active);
CREATE INDEX IF NOT EXISTS idx_content_resources_protection ON content_resources(tenant_id, protection_level);

CREATE TABLE IF NOT EXISTS offline_cache_entries (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    cached_at TEXT NOT NULL,
    last_access_check TEXT,
    last_access_allowed INTEGER NOT NULL DEFAULT 1,
    local_path TEXT NOT NULL DEFAULT '',
    origin_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, student_id, resource_id)
);

CREATE INDEX IF NOT EXISTS idx_offline_cache_tenant ON offline_cache_entries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_offline_cache_student ON offline_cache_entries(tenant_id, student_id);

CREATE TABLE IF NOT EXISTS live_sessions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    batch_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'live', 'ended', 'cancelled')),
    scheduled_start TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    ended_at TEXT,
    host_id TEXT,
    hand_raises TEXT NOT NULL DEFAULT '[]',
    polls TEXT NOT NULL DEFAULT '[]',
    recording_resource_id TEXT,
    notes TEXT NOT NULL DEFAULT '',
    origin_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_live_sessions_tenant ON live_sessions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_live_sessions_batch ON live_sessions(tenant_id, batch_id);
CREATE INDEX IF NOT EXISTS idx_live_sessions_status ON live_sessions(tenant_id, status);

CREATE TABLE IF NOT EXISTS viewer_session_tokens (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    token TEXT NOT NULL,
    watermark_text TEXT NOT NULL DEFAULT '',
    expires_at TEXT NOT NULL DEFAULT '',
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_viewer_tokens_tenant ON viewer_session_tokens(tenant_id);
CREATE INDEX IF NOT EXISTS idx_viewer_tokens_resource ON viewer_session_tokens(tenant_id, resource_id);
CREATE INDEX IF NOT EXISTS idx_viewer_tokens_token ON viewer_session_tokens(token);
