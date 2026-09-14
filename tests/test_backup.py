"""
Rotating SQLite backups + restore-from-backup recovery.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from models.base import (
    TenantContext,
    DataAccessLayer,
    create_backup,
    list_backups,
    restore_from_backup,
    backup_dir_for,
    BACKUP_KEEP,
    BACKUP_EVERY_N_WRITES,
)


class TestRotatingBackup(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.ctx = TenantContext(uuid.uuid4(), "offline-first")
        DataAccessLayer.close_all()

    def tearDown(self):
        DataAccessLayer.close_all()
        for p in [self.db_path, self.db_path + ".corrupted"]:
            try:
                os.unlink(p)
            except OSError:
                pass
        bdir = backup_dir_for(self.db_path)
        if bdir.is_dir():
            for f in bdir.iterdir():
                try:
                    f.unlink()
                except OSError:
                    pass
            try:
                bdir.rmdir()
            except OSError:
                pass

    def test_startup_creates_backup(self):
        dal = DataAccessLayer(self.ctx, db_path=self.db_path)
        backups = list_backups(self.db_path)
        self.assertGreaterEqual(len(backups), 1)
        DataAccessLayer.close_all()

    def test_backup_every_n_writes(self):
        dal = DataAccessLayer(self.ctx, db_path=self.db_path)
        before = len(list_backups(self.db_path))
        # Force small interval for test speed
        dal._backup_every = 5
        dal._write_count = 0
        for i in range(5):
            dal.create("students", {"name": f"S{i}", "roll": str(i)})
        after = len(list_backups(self.db_path))
        self.assertGreater(after, before)
        DataAccessLayer.close_all()

    def test_keeps_last_seven(self):
        dal = DataAccessLayer(self.ctx, db_path=self.db_path)
        for i in range(BACKUP_KEEP + 3):
            dal.create("students", {"name": f"X{i}"})
            create_backup(self.db_path, conn=dal._conn)
        backups = list_backups(self.db_path)
        self.assertLessEqual(len(backups), BACKUP_KEEP)
        DataAccessLayer.close_all()

    def test_recover_from_corrupted_primary(self):
        """Corrupt primary db; restore newest backup; data returns."""
        dal = DataAccessLayer(self.ctx, db_path=self.db_path)
        rid = dal.create(
            "students",
            {"name": "RecoverMe", "roll": "R001", "batch_id": "b1"},
        )
        # Explicit backup after data is written
        bak = create_backup(self.db_path, conn=dal._conn)
        self.assertIsNotNone(bak)
        self.assertTrue(bak.is_file())
        DataAccessLayer.close_all()

        # Corrupt primary file
        with open(self.db_path, "wb") as f:
            f.write(b"NOT_A_VALID_SQLITE_DATABASE_CORRUPTED")

        # Restore from the known-good backup (not merely "newest")
        used = restore_from_backup(self.db_path, backup_path=str(bak))
        self.assertEqual(used.resolve(), bak.resolve())

        # Data must be readable again
        dal2 = DataAccessLayer(self.ctx, db_path=self.db_path)
        row = dal2.get("students", rid)
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "RecoverMe")
        self.assertEqual(row["roll"], "R001")
        DataAccessLayer.close_all()

    def test_migrate_restore_cli(self):
        """scripts/migrate.py --restore path works."""
        import subprocess
        import sys

        dal = DataAccessLayer(self.ctx, db_path=self.db_path)
        rid = dal.create("students", {"name": "CLI Recover"})
        bak = create_backup(self.db_path, conn=dal._conn)
        self.assertIsNotNone(bak)
        rid_str = str(rid)
        tenant_str = str(self.ctx.tenant_id)
        DataAccessLayer.close_all()

        with open(self.db_path, "wb") as f:
            f.write(b"CORRUPT")

        root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
        DataAccessLayer.close_all()
        result = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "migrate.py"),
                "--db",
                self.db_path,
                "--restore",
                "--backup",
                str(bak),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(
            result.returncode, 0,
            msg=f"stdout={result.stdout!r} stderr={result.stderr!r}",
        )
        self.assertIn("Restored", result.stdout)

        # Verify in a fresh subprocess so no parent connection cache interferes
        verify = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import uuid; from models.base import TenantContext, DataAccessLayer; "
                    f"ctx=TenantContext(uuid.UUID('{tenant_str}')); "
                    f"dal=DataAccessLayer(ctx, db_path=r'{self.db_path}'); "
                    f"row=dal.get('students', uuid.UUID('{rid_str}')); "
                    "print(row['name'] if row else 'MISSING'); "
                    "DataAccessLayer.close_all()"
                ),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(verify.returncode, 0, msg=verify.stderr)
        self.assertEqual(verify.stdout.strip(), "CLI Recover", msg=verify.stdout + verify.stderr)

    def test_memory_skips_backup(self):
        dal = DataAccessLayer(self.ctx, db_path=":memory:")
        self.assertIsNone(dal.backup_now())
        for i in range(60):
            dal.create("students", {"name": f"m{i}"})
        # no crash, no files
        dal.close()


if __name__ == "__main__":
    unittest.main()
