"""Batch 3 — biometric devices + storage settings routes."""
from __future__ import annotations

import io
import os
import unittest

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")

from fastapi.testclient import TestClient
from api.main import create_api_app
from services.storage_service import LocalFsStorageProvider, GoogleDriveStorageProvider, build_storage_provider
from services.biometric_driver import PYZK_AVAILABLE


class TestStorageServiceUnit(unittest.TestCase):
    def test_local_fs_roundtrip(self):
        p = LocalFsStorageProvider("/tmp/cohortos-test-storage-b3")
        rid = p.upload("x/y.bin", io.BytesIO(b"abc"), "application/octet-stream")
        self.assertTrue(p.exists(rid))
        self.assertEqual(p.download(rid).read(), b"abc")
        self.assertTrue(p.delete(rid))

    def test_gdrive_unconfigured(self):
        g = GoogleDriveStorageProvider()
        self.assertFalse(g.is_configured())
        r = g.test_upload()
        self.assertFalse(r["ok"])


class TestBatch3Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_api_app(
            jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
            cloud_db=":memory:",
            auth_db=":memory:",
            founder_token=os.environ["COHORTOS_FOUNDER_TOKEN"],
        )
        cls.client = TestClient(cls.app)
        r = cls.client.post(
            "/auth/centre-trial",
            json={"centre_name": "B3 Centre", "owner_phone": "01719999003", "owner_name": "Owner"},
        )
        assert r.status_code == 200, r.text
        cls.tenant_id = r.json()["tenant_id"]
        otp = cls.client.post("/auth/request-otp", json={"phone": "01719999003"})
        body = otp.json()
        r2 = cls.client.post(
            "/auth/verify-otp",
            json={"otp_id": body["otp_id"], "code": body["_test_code"], "tenant_id": cls.tenant_id},
        )
        assert r2.status_code == 200, r2.text
        cls.headers = {"Authorization": f"Bearer {r2.json()['access_token']}"}
        # batch + student for link tests
        br = cls.client.post(
            f"/t/{cls.tenant_id}/batches",
            headers=cls.headers,
            json={"days": ["Sat"], "hour": 10, "name": "B"},
        )
        cls.batch_id = br.json().get("batch_id") or (br.json().get("batch") or {}).get("id")
        sr = cls.client.post(
            f"/t/{cls.tenant_id}/students",
            headers=cls.headers,
            json={"name": "Stu", "batch_id": cls.batch_id, "phone": "01718888003"},
        )
        sj = sr.json() if sr.status_code < 400 else {}
        cls.student_id = sj.get("student_id") or sj.get("id") or (sj.get("student") or {}).get("id")

    def test_biometric_status_includes_pyzk_flag(self):
        r = self.client.get(
            f"/t/{self.tenant_id}/attendance/biometric/status",
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("pyzk_available", r.json())
        self.assertEqual(r.json()["pyzk_available"], PYZK_AVAILABLE)

    def test_register_and_disable_device(self):
        r = self.client.post(
            f"/t/{self.tenant_id}/attendance/biometric/devices",
            headers=self.headers,
            json={"name": "Gate K60", "ip_address": "192.168.1.50", "port": 4370},
        )
        self.assertEqual(r.status_code, 200, r.text)
        did = r.json()["device_id"]
        self.assertTrue(did)
        self.assertIn("pyzk_available", r.json())

        tr = self.client.post(
            f"/t/{self.tenant_id}/attendance/biometric/devices/{did}/test",
            headers=self.headers,
            json={},
        )
        self.assertEqual(tr.status_code, 200, tr.text)
        # Without real device / maybe without pyzk — must not 500
        body = tr.json()
        self.assertIn("ok", body)
        if not PYZK_AVAILABLE:
            self.assertFalse(body["ok"])
            self.assertIn("message", body)

        dr = self.client.post(
            f"/t/{self.tenant_id}/attendance/biometric/devices/{did}/disable",
            headers=self.headers,
            json={},
        )
        self.assertEqual(dr.status_code, 200, dr.text)
        self.assertFalse(dr.json()["is_active"])

    def test_link_device_user(self):
        if not self.student_id:
            self.skipTest("no student")
        r = self.client.post(
            f"/t/{self.tenant_id}/attendance/biometric/link",
            headers=self.headers,
            json={"student_id": self.student_id, "device_user_id": "42"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["device_user_id"], "42")

    def test_storage_settings_and_test(self):
        r = self.client.get(
            f"/t/{self.tenant_id}/settings/storage",
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("provider", r.json())
        self.assertIn("configured", r.json())

        # Switch to local_fs so test upload can succeed
        pr = self.client.put(
            f"/t/{self.tenant_id}/settings/storage",
            headers=self.headers,
            json={"provider": "local_fs", "root": "/tmp/cohortos-b3-storage"},
        )
        self.assertEqual(pr.status_code, 200, pr.text)

        tr = self.client.post(
            f"/t/{self.tenant_id}/settings/storage/test",
            headers=self.headers,
            json={},
        )
        self.assertEqual(tr.status_code, 200, tr.text)
        self.assertTrue(tr.json().get("ok"), tr.text)


if __name__ == "__main__":
    unittest.main()
