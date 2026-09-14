-- CoachMate Portion 5: Exams / Results (SPEC Module 4)
-- Templates, exam instances, permanent results with section scores.
-- Offline-first; tenant-scoped. History never lost on roll/batch change.

PRAGMA foreign_keys = ON;

-- Reusable exam structures (default main-exam + custom)
CREATE TABLE IF NOT EXISTS exam_templates (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    is_open_book INTEGER NOT NULL DEFAULT 0,
    subject TEXT NOT NULL DEFAULT '',
    sections TEXT NOT NULL DEFAULT '[]',          -- JSON array
    is_active INTEGER NOT NULL DEFAULT 1,
    origin_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_exam_templates_tenant ON exam_templates(tenant_id);
CREATE INDEX IF NOT EXISTS idx_exam_templates_active ON exam_templates(tenant_id, is_active);

-- Concrete exam sittings (from template or ad-hoc)
CREATE TABLE IF NOT EXISTS exams (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    template_id TEXT,
    batch_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    exam_date TEXT NOT NULL,                      -- YYYY-MM-DD
    chapter_or_topic TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'scheduled', 'in_progress', 'completed', 'cancelled')),
    sections TEXT NOT NULL DEFAULT '[]',          -- JSON (copied/overridden from template)
    is_ad_hoc INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    origin_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_exams_tenant ON exams(tenant_id);
CREATE INDEX IF NOT EXISTS idx_exams_batch ON exams(tenant_id, batch_id);
CREATE INDEX IF NOT EXISTS idx_exams_date ON exams(tenant_id, exam_date);
CREATE INDEX IF NOT EXISTS idx_exams_topic ON exams(tenant_id, chapter_or_topic);
CREATE INDEX IF NOT EXISTS idx_exams_status ON exams(tenant_id, status);

-- Permanent student results (HISTORY_TABLES entry: exam_results)
-- 005_admission.sql left a minimal stub for roll-migration history.
-- Replace it with the full schema required by Module 4.
DROP TABLE IF EXISTS exam_results;
CREATE TABLE exam_results (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    exam_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    batch_id TEXT NOT NULL DEFAULT '',
    roll TEXT NOT NULL DEFAULT '',
    exam_date TEXT NOT NULL DEFAULT '',
    chapter_or_topic TEXT NOT NULL DEFAULT '',
    section_scores TEXT NOT NULL DEFAULT '[]',    -- JSON [{key, marks_obtained, max_marks, notes}]
    total_obtained REAL NOT NULL DEFAULT 0,
    total_max REAL NOT NULL DEFAULT 0,
    percentage REAL NOT NULL DEFAULT 0,
    is_absent INTEGER NOT NULL DEFAULT 0,
    entered_by TEXT,
    notes TEXT NOT NULL DEFAULT '',
    origin_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, exam_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_exam_results_tenant ON exam_results(tenant_id);
CREATE INDEX IF NOT EXISTS idx_exam_results_student ON exam_results(tenant_id, student_id);
CREATE INDEX IF NOT EXISTS idx_exam_results_exam ON exam_results(tenant_id, exam_id);
CREATE INDEX IF NOT EXISTS idx_exam_results_batch ON exam_results(tenant_id, batch_id);
CREATE INDEX IF NOT EXISTS idx_exam_results_topic ON exam_results(tenant_id, chapter_or_topic);
CREATE INDEX IF NOT EXISTS idx_exam_results_date ON exam_results(tenant_id, exam_date);
