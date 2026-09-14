"""
Backend v1 — Part C: real cloud sync (push/pull, modes, device destruction).
"""

from __future__ import annotations

import os
import uuid
import unittest
import tempfile

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")

from models.base import TenantContext, DataAccessLayer
from models.sync import SyncOperation
from services.config_service import ConfigService
from services.sync_engine import SyncEngine
from api.sync_remote import CloudSyncStore
from api.transport import InProcessTransport
from api.main import create_api_app
from fastapi.testclient import TestClient


def _engine(tenant_id, transport=None, mode="offline-first", device_id=None, db_path=":memory:"):
    ctx = TenantContext(uuid.UUID(str(tenant_id)), mode)
    cfg = ConfigService(ctx)
    eng = SyncEngine(
        ctx,
        cfg,
        db_path=db_path,
        device_id=device_id or str(uuid.uuid4()),
        transport=transport,
    )
    eng.initialize()
    return eng


class TestCloudSyncStore(unittest.TestCase):
    def test_push_pull(self):
        store = CloudSyncStore(":memory:")
        tid = str(uuid.uuid4())
        store.push(
            tid,
            [
                {
                    "op_id": "op1",
                    "operation_type": "create",
                    "table_name": "students",
                    "record_id": str(uuid.uuid4()),
                    "new_state": {"name": "A"},
                }
            ],
            device_id="devA",
        )
        out = store.pull(tid, since_seq=0, exclude_device="")
        self.assertEqual(len(out["operations"]), 1)
        self.assertEqual(out["operations"][0]["new_state"]["name"], "A")


class TestSyncEngineRemote(unittest.TestCase):
    def test_offline_degrades_to_queue_only(self):
        store = CloudSyncStore(":memory:")
        transport = InProcessTransport(store)
        tid = uuid.uuid4()
        eng = _engine(tid, transport=transport)
        eng.queue_operation(
            SyncOperation(
                operation_type="create",
                table_name="students",
                record_id=str(uuid.uuid4()),
                tenant_id=str(tid),
                new_state={"name": "OfflineKid"},
            )
        )
        eng.set_online(False)
        result = eng.sync_now()
        self.assertEqual(result["push"]["status"], "offline")
        self.assertGreaterEqual(result["push"]["pending"], 1)
        # Still pending locally
        self.assertGreaterEqual(len(eng.get_pending_operations()), 1)

    def test_online_push_and_catchup(self):
        store = CloudSyncStore(":memory:")
        transport = InProcessTransport(store)
        tid = uuid.uuid4()
        eng = _engine(tid, transport=transport, device_id="A")
        eng.queue_operation(
            SyncOperation(
                operation_type="create",
                table_name="students",
                record_id=str(uuid.uuid4()),
                tenant_id=str(tid),
                new_state={"name": "OnlineKid"},
            )
        )
        eng.set_online(True)
        result = eng.sync_now()
        self.assertEqual(result["push"]["status"], "ok")
        self.assertGreaterEqual(result["push"]["pushed"], 1)
        # Queue cleared
        self.assertEqual(len(eng.get_pending_operations()), 0)

    def test_offline_first_then_reconnect(self):
        store = CloudSyncStore(":memory:")
        transport = InProcessTransport(store)
        tid = uuid.uuid4()
        eng = _engine(tid, transport=transport, mode="offline-first", device_id="desk")
        rid = str(uuid.uuid4())
        eng.queue_operation(
            SyncOperation(
                operation_type="create",
                table_name="students",
                record_id=rid,
                tenant_id=str(tid),
                new_state={"name": "DeskStudent", "id": rid},
            )
        )
        eng.set_online(False)
        eng.sync_now()
        self.assertGreaterEqual(len(eng.get_pending_operations()), 1)
        eng.set_online(True)
        result = eng.sync_now()
        self.assertEqual(result["push"]["status"], "ok")
        pulled = store.pull(str(tid), since_seq=0)
        self.assertTrue(any(o["new_state"].get("name") == "DeskStudent" for o in pulled["operations"]))

    def test_device_a_destroyed_device_b_recovers(self):
        """
        Create data on Device A, complete sync, destroy A,
        fresh Device B (cloud-first) pulls and has the data.
        """
        store = CloudSyncStore(":memory:")
        transport = InProcessTransport(store)
        tid = uuid.uuid4()

        # Device A
        eng_a = _engine(tid, transport=transport, device_id="device-A")
        rid = str(uuid.uuid4())
        eng_a.queue_operation(
            SyncOperation(
                operation_type="create",
                table_name="students",
                record_id=rid,
                tenant_id=str(tid),
                new_state={"name": "SurvivesLaptopDeath", "roll": "X1", "id": rid},
            )
        )
        # Also write locally so A has it
        eng_a.data_access.create(
            "students",
            {"name": "SurvivesLaptopDeath", "roll": "X1"},
        )
        # Overwrite with known id via direct store for pull apply
        eng_a.sync_now()

        # Laptop dies — drop eng_a, no more access
        del eng_a

        # Device B fresh install
        eng_b = _engine(tid, transport=transport, mode="cloud-first", device_id="device-B")
        # Seed local with empty; pull remote
        pull = eng_b.pull_from_remote()
        self.assertEqual(pull["status"], "ok")
        self.assertGreaterEqual(pull["applied"], 1)

        # Confirm cloud still has the op (source of truth for B)
        cloud = store.pull(str(tid), since_seq=0, exclude_device="")
        names = [o["new_state"].get("name") for o in cloud["operations"]]
        self.assertIn("SurvivesLaptopDeath", names)

    def test_hybrid_desk_and_teacher_converge(self):
        store = CloudSyncStore(":memory:")
        transport = InProcessTransport(store)
        tid = uuid.uuid4()

        desk = _engine(tid, transport=transport, mode="hybrid", device_id="desk")
        teacher = _engine(tid, transport=transport, mode="hybrid", device_id="teacher")

        rid = str(uuid.uuid4())
        desk.queue_operation(
            SyncOperation(
                operation_type="create",
                table_name="attendance_records",
                record_id=rid,
                tenant_id=str(tid),
                new_state={"student_id": "s1", "status": "present", "id": rid},
            )
        )
        desk.sync_now()

        result = teacher.sync_now()
        self.assertEqual(result["pull"]["status"], "ok")
        self.assertGreaterEqual(result["pull"]["applied"], 1)

    def test_http_sync_endpoints(self):
        tenant_id = str(uuid.uuid4())
        api = create_api_app(jwt_secret=os.environ["COHORTOS_JWT_SECRET"])
        client = TestClient(api)
        registry = api.state.registry
        cm = registry.get_app(tenant_id)
        cm.accounts.create_account(phone="01718880001")
        otp = client.post(
            "/auth/request-otp",
            json={"phone": "01718880001", "tenant_id": tenant_id},
        ).json()
        tokens = client.post(
            "/auth/verify-otp",
            json={"otp_id": otp["otp_id"], "code": otp["_test_code"], "tenant_id": tenant_id},
        ).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        rid = str(uuid.uuid4())
        push = client.post(
            "/sync/push",
            headers=headers,
            json={
                "device_id": "http-dev",
                "operations": [
                    {
                        "op_id": "http-op-1",
                        "operation_type": "create",
                        "table_name": "students",
                        "record_id": rid,
                        "new_state": {"name": "HTTP Student"},
                    }
                ],
            },
        )
        self.assertEqual(push.status_code, 200)
        self.assertGreaterEqual(push.json()["accepted"], 1)

        pull = client.post(
            "/sync/pull",
            headers=headers,
            json={"since_seq": 0, "device_id": "other"},
        )
        self.assertEqual(pull.status_code, 200)
        ops = pull.json()["operations"]
        self.assertTrue(any(o["new_state"].get("name") == "HTTP Student" for o in ops))


if __name__ == "__main__":
    unittest.main()
