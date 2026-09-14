"""Batch 2 — conflict log, backup export, license status routes."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")

from fastapi.testclient import TestClient
from api.main import create_api_app


class TestBatch2Routes(unittest.TestCase):
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
            json={
                "centre_name": "Batch2 Centre",
                "owner_phone": "01719999002",
                "owner_name": "Owner Two",
            },
        )
        assert r.status_code == 200, r.text
        cls.tenant_id = r.json()["tenant_id"]
        otp = cls.client.post("/auth/request-otp", json={"phone": "01719999002"})
        assert otp.status_code == 200, otp.text
        body = otp.json()
        r2 = cls.client.post(
            "/auth/verify-otp",
            json={
                "otp_id": body["otp_id"],
                "code": body["_test_code"],
                "tenant_id": body.get("tenant_id") or cls.tenant_id,
            },
        )
        assert r2.status_code == 200, r2.text
        cls.headers = {"Authorization": f"Bearer {r2.json()['access_token']}"}

    def test_list_conflicts_empty(self):
        r = self.client.get(
            f"/t/{self.tenant_id}/sync/conflicts",
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("conflicts", r.json())

    def test_backup_status(self):
        r = self.client.get(
            f"/t/{self.tenant_id}/backup/status",
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("wal_active", data)
        self.assertIn("journal_mode", data)
        self.assertIn("backups", data)

    def test_backup_export(self):
        r = self.client.post(
            f"/t/{self.tenant_id}/backup/export",
            headers=self.headers,
            json={},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get("ok"))
        self.assertIn("export", r.json())

    def test_license_status(self):
        r = self.client.get(
            f"/t/{self.tenant_id}/license/status",
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("locked", data)
        self.assertFalse(data["locked"])  # fresh trial not locked


if __name__ == "__main__":
    unittest.main()
