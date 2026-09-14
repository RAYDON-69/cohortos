"""
Prove TokenService session families and SyncEngine pull cursor survive
a full process restart (new instances, same SQLite files).
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault(
    "COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod"
)

from models.base import TenantContext, DataAccessLayer
from models.sync import SyncOperation
from services.config_service import ConfigService
from services.sync_engine import SyncEngine
from api.auth import TokenService
from api.sync_remote import CloudSyncStore
from api.transport import InProcessTransport


class TestTokenServiceSurvivesRestart(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix="_auth.db")
        os.close(fd)
        DataAccessLayer.close_all()

    def tearDown(self):
        DataAccessLayer.close_all()
        for p in (self.db_path, self.db_path + "-wal", self.db_path + "-shm"):
            try:
                os.unlink(p)
            except OSError:
                pass

    def test_unused_refresh_works_after_restart(self):
        secret = os.environ["COHORTOS_JWT_SECRET"]
        tenant_id = str(uuid.uuid4())
        account_id = str(uuid.uuid4())

        # Process 1: issue refresh
        dal1 = DataAccessLayer(
            TenantContext(uuid.UUID("00000000-0000-4000-8000-000000000099")),
            db_path=self.db_path,
        )
        ts1 = TokenService(secret, data_layer=dal1)
        refresh, family_id = ts1.issue_refresh(account_id, tenant_id)
        DataAccessLayer.close_all()  # simulate process exit

        # Process 2: new TokenService, same DB — unused refresh must still rotate
        dal2 = DataAccessLayer(
            TenantContext(uuid.UUID("00000000-0000-4000-8000-000000000099")),
            db_path=self.db_path,
        )
        ts2 = TokenService(secret, data_layer=dal2)
        access, new_refresh, fid = ts2.rotate_refresh(refresh)
        self.assertEqual(fid, family_id)
        self.assertTrue(access)
        self.assertTrue(new_refresh)
        self.assertNotEqual(refresh, new_refresh)
        DataAccessLayer.close_all()

        # Process 3: reuse of the pre-restart token must revoke (it was rotated)
        dal3 = DataAccessLayer(
            TenantContext(uuid.UUID("00000000-0000-4000-8000-000000000099")),
            db_path=self.db_path,
        )
        ts3 = TokenService(secret, data_layer=dal3)
        from api.auth import TokenReuseError
        with self.assertRaises(TokenReuseError):
            ts3.rotate_refresh(refresh)
        DataAccessLayer.close_all()


class TestSyncCursorSurvivesRestart(unittest.TestCase):
    def setUp(self):
        fd, self.domain_db = tempfile.mkstemp(suffix="_domain.db")
        os.close(fd)
        fd, self.sync_db = tempfile.mkstemp(suffix="_sync.db")
        os.close(fd)
        DataAccessLayer.close_all()
        self.store = CloudSyncStore(":memory:")
        self.transport = InProcessTransport(self.store)
        self.tenant_id = uuid.uuid4()
        self.device_id = "device-persist-1"

    def tearDown(self):
        DataAccessLayer.close_all()
        for p in (self.domain_db, self.sync_db):
            for s in ("", "-wal", "-shm"):
                try:
                    os.unlink(p + s)
                except OSError:
                    pass

    def _make_engine(self):
        ctx = TenantContext(self.tenant_id, "offline-first")
        cfg = ConfigService(ctx)
        eng = SyncEngine(
            ctx,
            cfg,
            db_path=self.sync_db,
            device_id=self.device_id,
            transport=self.transport,
            domain_db_path=self.domain_db,
        )
        eng.initialize()
        return eng

    def test_pull_cursor_resumes_after_restart(self):
        # Seed cloud with two batches of ops
        tid = str(self.tenant_id)
        for i in range(3):
            self.store.push(
                tid,
                [
                    {
                        "op_id": f"op-a-{i}",
                        "operation_type": "create",
                        "table_name": "students",
                        "record_id": str(uuid.uuid4()),
                        "new_state": {"name": f"A{i}"},
                    }
                ],
                device_id="other",
            )

        eng1 = self._make_engine()
        r1 = eng1.pull_from_remote()
        self.assertEqual(r1["status"], "ok")
        self.assertGreaterEqual(r1["applied"], 3)
        cursor_after_first = eng1._pull_cursor
        self.assertGreater(cursor_after_first, 0)
        DataAccessLayer.close_all()

        # More ops arrive while "process is down"
        for i in range(2):
            self.store.push(
                tid,
                [
                    {
                        "op_id": f"op-b-{i}",
                        "operation_type": "create",
                        "table_name": "students",
                        "record_id": str(uuid.uuid4()),
                        "new_state": {"name": f"B{i}"},
                    }
                ],
                device_id="other",
            )

        # Process 2: new engine, same domain DB + device_id
        eng2 = self._make_engine()
        self.assertEqual(
            eng2._pull_cursor,
            cursor_after_first,
            "cursor must resume from disk, not reset to 0",
        )
        r2 = eng2.pull_from_remote()
        self.assertEqual(r2["status"], "ok")
        # Only the 2 new ops should apply (not full history)
        self.assertEqual(r2["applied"], 2)
        DataAccessLayer.close_all()


class TestCombinedRestartScenario(unittest.TestCase):
    """The exact mid-session restart scenario that broke."""

    def test_refresh_and_cursor_together(self):
        secret = os.environ["COHORTOS_JWT_SECRET"]
        fd1, auth_db = tempfile.mkstemp(suffix="_auth.db")
        os.close(fd1)
        fd2, domain_db = tempfile.mkstemp(suffix="_dom.db")
        os.close(fd2)
        DataAccessLayer.close_all()

        try:
            tenant_id = str(uuid.uuid4())
            account_id = str(uuid.uuid4())
            device_id = "combo-device"

            # --- live session ---
            auth_dal = DataAccessLayer(
                TenantContext(uuid.UUID("00000000-0000-4000-8000-000000000099")),
                db_path=auth_db,
            )
            ts = TokenService(secret, data_layer=auth_dal)
            refresh, family = ts.issue_refresh(account_id, tenant_id)

            store = CloudSyncStore(":memory:")
            transport = InProcessTransport(store)
            tid = uuid.UUID(tenant_id)
            ctx = TenantContext(tid, "offline-first")
            eng = SyncEngine(
                ctx,
                ConfigService(ctx),
                device_id=device_id,
                transport=transport,
                domain_db_path=domain_db,
            )
            eng.initialize()
            store.push(
                tenant_id,
                [
                    {
                        "op_id": "combo-1",
                        "operation_type": "create",
                        "table_name": "students",
                        "record_id": str(uuid.uuid4()),
                        "new_state": {"name": "BeforeRestart"},
                    }
                ],
                device_id="server",
            )
            eng.pull_from_remote()
            saved_cursor = eng._pull_cursor
            self.assertGreater(saved_cursor, 0)

            # --- process dies ---
            DataAccessLayer.close_all()
            del ts, eng, auth_dal

            # --- process restarts ---
            auth_dal2 = DataAccessLayer(
                TenantContext(uuid.UUID("00000000-0000-4000-8000-000000000099")),
                db_path=auth_db,
            )
            ts2 = TokenService(secret, data_layer=auth_dal2)
            access, new_refresh, fid = ts2.rotate_refresh(refresh)
            self.assertEqual(fid, family)
            self.assertTrue(access)

            eng2 = SyncEngine(
                TenantContext(tid, "offline-first"),
                ConfigService(TenantContext(tid, "offline-first")),
                device_id=device_id,
                transport=transport,
                domain_db_path=domain_db,
            )
            eng2.initialize()
            self.assertEqual(eng2._pull_cursor, saved_cursor)

            DataAccessLayer.close_all()
        finally:
            DataAccessLayer.close_all()
            for p in (auth_db, domain_db):
                for s in ("", "-wal", "-shm"):
                    try:
                        os.unlink(p + s)
                    except OSError:
                        pass


if __name__ == "__main__":
    unittest.main()
