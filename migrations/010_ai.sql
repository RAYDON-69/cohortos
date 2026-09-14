-- CoachMate Portion 8: AI Solve + Teach (SPEC Module 9)
-- Threads, messages, generated items, style profiles, cache, quota.
-- Offline-first; tenant-scoped.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ai_threads (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    message_count INTEGER NOT NULL DEFAULT 0,
    last_message_at TEXT,
    flagged_for_teacher INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_threads_student ON ai_threads(tenant_id, student_id);

CREATE TABLE IF NOT EXISTS ai_messages (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    question_type TEXT NOT NULL DEFAULT 'written',
    subject TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    board TEXT NOT NULL DEFAULT '',
    answer_block TEXT NOT NULL DEFAULT '',
    how_block TEXT NOT NULL DEFAULT '',
    why_block TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    grounded INTEGER NOT NULL DEFAULT 0,
    source_chunk_ids TEXT NOT NULL DEFAULT '[]',
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_reason TEXT NOT NULL DEFAULT '',
    model_tier TEXT NOT NULL DEFAULT 'cheap',
    cached INTEGER NOT NULL DEFAULT 0,
    teacher_annotation TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_messages_thread ON ai_messages(tenant_id, thread_id);
CREATE INDEX IF NOT EXISTS idx_ai_messages_student ON ai_messages(tenant_id, student_id);

CREATE TABLE IF NOT EXISTS ai_generated_items (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'needs_review',
    confidence REAL NOT NULL DEFAULT 0,
    grounded INTEGER NOT NULL DEFAULT 0,
    source_chunk_ids TEXT NOT NULL DEFAULT '[]',
    review_reason TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL DEFAULT '',
    approved_by TEXT,
    approved_at TEXT,
    rejected_by TEXT,
    rejected_at TEXT,
    reject_reason TEXT NOT NULL DEFAULT '',
    history TEXT NOT NULL DEFAULT '[]',
    impact_score REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_items_status ON ai_generated_items(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_ai_items_subject ON ai_generated_items(tenant_id, subject);

CREATE TABLE IF NOT EXISTS ai_style_profiles (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    style_notes TEXT NOT NULL DEFAULT '',
    terminology TEXT NOT NULL DEFAULT '[]',
    sign_conventions TEXT NOT NULL DEFAULT '',
    difficulty TEXT NOT NULL DEFAULT 'medium',
    few_shot_examples TEXT NOT NULL DEFAULT '[]',
    preferred_language TEXT NOT NULL DEFAULT 'en',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_style_subject ON ai_style_profiles(tenant_id, subject);

CREATE TABLE IF NOT EXISTS ai_query_cache (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    query_normalized TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    answer_block TEXT NOT NULL DEFAULT '',
    how_block TEXT NOT NULL DEFAULT '',
    why_block TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    source_chunk_ids TEXT NOT NULL DEFAULT '[]',
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_cache_hash ON ai_query_cache(tenant_id, query_hash);

CREATE TABLE IF NOT EXISTS ai_quota_usage (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    date TEXT NOT NULL,
    mcq_count INTEGER NOT NULL DEFAULT 0,
    written_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, student_id, date)
);
CREATE INDEX IF NOT EXISTS idx_ai_quota_student ON ai_quota_usage(tenant_id, student_id, date);
