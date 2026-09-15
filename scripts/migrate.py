#!/usr/bin/env python3
"""
Apply CohortOS SQL migrations to a SQLite database.

- 001 / 002 are PostgreSQL reference schemas (skipped for SQLite targets).
- 003–009 are written for SQLite / offline-first and are applied in order.
- Idempotent: uses a schema_migrations table.

Usage:
  python scripts/migrate.py --db /path/to/cohortos.db
  python scripts/migrate.py --db :memory: --dry-run
  python scripts/migrate.py --db /path/to/cohortos.db --restore
  python scripts/migrate.py --db /path/to/cohortos.db --restore --backup /path/to/backup.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations"

# Only SQLite-compatible migrations for the offline path
SQLITE_MIGRATIONS = [
    "003_sync_queue.sql",
    "004_notifications.sql",
    "005_admission.sql",
    "006_attendance.sql",
    "007_payments.sql",
    "008_exams.sql",
    "009_content.sql",
    "010_ai.sql",
    "011_accounts.sql",
    "012_saas.sql",
]


def apply_migrations(db_path: str, dry_run: bool = False) -> int:
    if dry_run:
        print(f"[dry-run] would apply to {db_path}:")
        for name in SQLITE_MIGRATIONS:
            print(f"  - {name}")
        return 0

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    # Domain document store used by DataAccessLayer
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _records (
            table_name TEXT NOT NULL,
            id         TEXT NOT NULL,
            tenant_id  TEXT NOT NULL,
            data       TEXT NOT NULL,
            is_active  INTEGER NOT NULL DEFAULT 1,
            created_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (table_name, id)
        );
        CREATE INDEX IF NOT EXISTS idx_records_tenant
            ON _records (table_name, tenant_id);
    """)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    applied = {
        row[0]
        for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
    }

    count = 0
    for name in SQLITE_MIGRATIONS:
        if name in applied:
            print(f"skip  {name} (already applied)")
            continue
        path = MIGRATIONS_DIR / name
        if not path.exists():
            print(f"WARN  missing {path}")
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (?)", (name,)
            )
            conn.commit()
            print(f"apply {name}")
            count += 1
        except sqlite3.Error as e:
            conn.rollback()
            print(f"FAIL  {name}: {e}", file=sys.stderr)
            conn.close()
            return 1

    conn.close()
    print(f"Done. {count} migration(s) applied to {db_path}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CohortOS SQLite migration runner")
    parser.add_argument(
        "--db",
        default=os.environ.get("COHORTOS_DB", "cohortos.db"),
        help="SQLite database path (default: cohortos.db or $COHORTOS_DB)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore primary db from the newest rotating backup (or --backup)",
    )
    parser.add_argument(
        "--backup",
        default=None,
        help="Specific backup file to restore when using --restore",
    )
    args = parser.parse_args(argv)
    if args.restore:
        # Import here so migrate.py still runs if models path differs
        sys.path.insert(0, str(ROOT))
        from models.base import restore_from_backup, list_backups
        try:
            used = restore_from_backup(args.db, backup_path=args.backup)
            print(f"Restored {args.db} from {used}")
            return apply_migrations(args.db, dry_run=args.dry_run)
        except Exception as e:
            print(f"Restore failed: {e}", file=sys.stderr)
            backups = list_backups(args.db)
            if backups:
                print("Available backups:", file=sys.stderr)
                for b in backups:
                    print(f"  {b}", file=sys.stderr)
            return 1
    return apply_migrations(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
