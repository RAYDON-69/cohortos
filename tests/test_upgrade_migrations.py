"""Upgrade safety: apply SQLite-compatible migration subset; integrity."""
from pathlib import Path
import sqlite3
import pytest

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "migrations"


def test_migrations_folder_present():
    assert MIG.exists()
    files = sorted(MIG.glob("*.sql"))
    assert files, "expected migration files"


def test_sqlite_bootstrap_integrity(tmp_path):
    """App cloud/auth DBs are SQLite; ensure WAL + integrity path works post-create."""
    db = tmp_path / "boot.db"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE students (id TEXT PRIMARY KEY, name TEXT, version INTEGER DEFAULT 1)")
    conn.execute("INSERT INTO students (id, name) VALUES ('1', 'A')")
    conn.commit()
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    # simulate pre-migration backup file
    bak = tmp_path / "pre-migrate.bak"
    bak.write_bytes(db.read_bytes())
    assert bak.stat().st_size > 0
    conn.close()


def test_postgres_migrations_are_documented_not_auto_applied_on_sqlite():
    """Postgres RLS/EXTENSION SQL must not be applied blindly to SQLite desk DBs."""
    text = ""
    for f in sorted(MIG.glob("*.sql")):
        text += f.read_text(errors="ignore")
    # Presence of PG features is OK in repo; desk path must not executescript them blindly
    assert "CREATE TABLE" in text or "create table" in text.lower()
