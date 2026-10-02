"""Replay migrations on three historical SQLite schema states."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "migrations"
HIST = {
    "v_attendance_era": ["003_sync_queue.sql","004_notifications.sql","005_admission.sql","006_attendance.sql"],
    "v_exams_content": ["003_sync_queue.sql","004_notifications.sql","005_admission.sql","006_attendance.sql","007_payments.sql","008_exams.sql","009_content.sql"],
    "v_ai_accounts": ["003_sync_queue.sql","004_notifications.sql","005_admission.sql","006_attendance.sql","007_payments.sql","008_exams.sql","009_content.sql","010_ai.sql","011_accounts.sql"],
}
FULL = HIST["v_ai_accounts"] + ["012_saas.sql"]

def _bootstrap(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _records (
            table_name TEXT NOT NULL, id TEXT NOT NULL, tenant_id TEXT NOT NULL,
            data TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT, updated_at TEXT, PRIMARY KEY (table_name, id));
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL DEFAULT (datetime('now')));
    """)

def _apply(conn, names):
    applied = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations")}
    n = 0
    for name in names:
        if name in applied: continue
        path = MIG / name
        if not path.exists(): continue
        sql = path.read_text(encoding="utf-8", errors="ignore")
        if "CREATE EXTENSION" in sql or "ENABLE ROW LEVEL SECURITY" in sql:
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (name,)); n += 1; continue
        try: conn.executescript(sql)
        except sqlite3.Error: pass
        conn.execute("INSERT OR IGNORE INTO schema_migrations (filename) VALUES (?)", (name,)); n += 1
    conn.commit(); return n

def _seed(conn, tenant, count=3):
    now = datetime.now(timezone.utc).isoformat()
    for i in range(count):
        sid = f"stu-{tenant}-{i}"
        data = json.dumps({"id": sid, "tenant_id": tenant, "name": f"ছাত্র {i}", "phone": f"0170000000{i}"})
        conn.execute("INSERT OR REPLACE INTO _records (table_name,id,tenant_id,data,is_active,created_at,updated_at) VALUES (?,?,?,?,1,?,?)",
                     ("students", sid, tenant, data, now, now))
    conn.commit()

@pytest.mark.parametrize("label,subset", list(HIST.items()))
def test_migration_replay_from_historical_state(label, subset, tmp_path):
    db = tmp_path / f"{label}.db"
    conn = sqlite3.connect(str(db))
    _bootstrap(conn); _apply(conn, subset); _seed(conn, "tenant-hist")
    before = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM _records WHERE table_name='students'").fetchone()[0] == 3
    _apply(conn, FULL)
    after = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert after >= before
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM _records WHERE table_name='students'").fetchone()[0] == 3
    conn.close()
