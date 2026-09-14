"""
Prove DataAccessLayer SQLite persistence across simulated process restarts.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid

from models.base import TenantContext, DataAccessLayer


class TestSQLitePersistence(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.tenant_id = uuid.uuid4()
        self.ctx = TenantContext(self.tenant_id, "offline-first")

    def tearDown(self):
        DataAccessLayer.close_all()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass
        for suffix in ("-wal", "-shm"):
            try:
                os.unlink(self.db_path + suffix)
            except OSError:
                pass

    def test_create_survives_restart(self):
        dal1 = DataAccessLayer(self.ctx, db_path=self.db_path)
        rid = dal1.create(
            "students",
            {"name": "Rahim", "roll": "02114001", "batch_id": "b1"},
        )
        dal1.close()
        DataAccessLayer.close_all()  # simulate process exit

        dal2 = DataAccessLayer(self.ctx, db_path=self.db_path)
        row = dal2.get("students", rid)
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "Rahim")
        self.assertEqual(row["roll"], "02114001")
        self.assertEqual(row["tenant_id"], str(self.tenant_id))
        dal2.close()
        DataAccessLayer.close_all()

    def test_update_survives_restart(self):
        dal1 = DataAccessLayer(self.ctx, db_path=self.db_path)
        rid = dal1.create("students", {"name": "Karim", "roll": "001"})
        dal1.update(rid and rid, {"name": "Karim Updated"}) if False else None
        dal1.update("students", rid, {"name": "Karim Updated", "notes": "ok"})
        DataAccessLayer.close_all()

        dal2 = DataAccessLayer(self.ctx, db_path=self.db_path)
        row = dal2.get("students", rid)
        self.assertEqual(row["name"], "Karim Updated")
        self.assertEqual(row["notes"], "ok")
        DataAccessLayer.close_all()

    def test_soft_delete_survives_restart(self):
        dal1 = DataAccessLayer(self.ctx, db_path=self.db_path)
        rid = dal1.create("students", {"name": "Gone"})
        self.assertTrue(dal1.delete("students", rid))
        DataAccessLayer.close_all()

        dal2 = DataAccessLayer(self.ctx, db_path=self.db_path)
        row = dal2.get("students", rid)
        self.assertIsNotNone(row)
        self.assertFalse(row.get("is_active"))
        DataAccessLayer.close_all()

    def test_tenant_isolation_on_disk(self):
        ctx_a = TenantContext(uuid.uuid4(), "offline-first")
        ctx_b = TenantContext(uuid.uuid4(), "offline-first")
        dal_a = DataAccessLayer(ctx_a, db_path=self.db_path)
        dal_b = DataAccessLayer(ctx_b, db_path=self.db_path)
        rid = dal_a.create("students", {"name": "OnlyA"})
        self.assertIsNone(dal_b.get("students", rid))
        self.assertEqual(len(dal_b.get_all("students")), 0)
        self.assertEqual(len(dal_a.get_all("students")), 1)
        DataAccessLayer.close_all()

        # After restart isolation holds
        dal_a2 = DataAccessLayer(ctx_a, db_path=self.db_path)
        dal_b2 = DataAccessLayer(ctx_b, db_path=self.db_path)
        self.assertEqual(len(dal_a2.get_all("students")), 1)
        self.assertEqual(len(dal_b2.get_all("students")), 0)
        DataAccessLayer.close_all()

    def test_complex_json_roundtrip(self):
        dal1 = DataAccessLayer(self.ctx, db_path=self.db_path)
        rid = dal1.create(
            "content_resources",
            {
                "title": "Notes",
                "batch_ids": ["b1", "b2"],
                "access_rules": {"operator": "AND", "rules": [{"kind": "paid_up"}]},
            },
        )
        DataAccessLayer.close_all()

        dal2 = DataAccessLayer(self.ctx, db_path=self.db_path)
        row = dal2.get("content_resources", rid)
        self.assertEqual(row["batch_ids"], ["b1", "b2"])
        self.assertEqual(row["access_rules"]["operator"], "AND")
        DataAccessLayer.close_all()

    def test_memory_default_isolated(self):
        """:memory: instances must not share data (test isolation)."""
        a = DataAccessLayer(self.ctx, db_path=":memory:")
        b = DataAccessLayer(self.ctx, db_path=":memory:")
        rid = a.create("students", {"name": "MemOnly"})
        self.assertIsNotNone(a.get("students", rid))
        self.assertIsNone(b.get("students", rid))
        a.close()
        b.close()

    def test_app_with_file_db_persists(self):
        from services.app import create_app

        app1 = create_app(tenant_id=self.tenant_id, db_path=self.db_path)
        summary = app1.bootstrap_centre(
            name="Persist Centre", code="PERS1", create_sample_batches=False
        )
        centre_id = summary["centre_id"]
        DataAccessLayer.close_all()

        app2 = create_app(tenant_id=self.tenant_id, db_path=self.db_path)
        centres = app2.data.get_all_centres()
        self.assertEqual(len(centres), 1)
        self.assertEqual(centres[0]["name"], "Persist Centre")
        self.assertEqual(str(centres[0]["id"]), centre_id)
        DataAccessLayer.close_all()

    def test_ensure_migrated_idempotent(self):
        dal = DataAccessLayer(self.ctx, db_path=self.db_path, auto_migrate=True)
        n1 = dal.ensure_migrated()
        n2 = dal.ensure_migrated()
        self.assertEqual(n2, 0)  # second pass applies nothing
        DataAccessLayer.close_all()


if __name__ == "__main__":
    unittest.main()
