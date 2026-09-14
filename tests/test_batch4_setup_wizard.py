"""Batch 4 — centre setup wizard eligibility (blocked once batches exist)."""
from __future__ import annotations

import os
import unittest
import itertools

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")

from fastapi.testclient import TestClient
from api.main import create_api_app

_phone = itertools.count(1719999100)


class TestSetupWizard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_api_app(
            jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
            cloud_db=":memory:",
            auth_db=":memory:",
            founder_token=os.environ["COHORTOS_FOUNDER_TOKEN"],
        )
        cls.client = TestClient(cls.app)

    def _fresh_tenant(self):
        n = next(_phone)
        phone = f"01{n:09d}"[-11:]
        r = self.client.post(
            "/auth/centre-trial",
            json={"centre_name": f"Wiz {phone}", "owner_phone": phone, "owner_name": "Owner"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        tenant_id = r.json()["tenant_id"]
        otp = self.client.post("/auth/request-otp", json={"phone": phone})
        body = otp.json()
        r2 = self.client.post(
            "/auth/verify-otp",
            json={
                "otp_id": body["otp_id"],
                "code": body["_test_code"],
                "tenant_id": body.get("tenant_id") or tenant_id,
            },
        )
        self.assertEqual(r2.status_code, 200, r2.text)
        headers = {"Authorization": f"Bearer {r2.json()['access_token']}"}
        return tenant_id, headers

    def test_needs_wizard_when_zero_batches(self):
        tenant_id, headers = self._fresh_tenant()
        r = self.client.get(f"/t/{tenant_id}/setup/status", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertTrue(data["needs_wizard"])
        self.assertEqual(data["batch_count"], 0)

    def test_first_batch_then_wizard_closed(self):
        tenant_id, headers = self._fresh_tenant()
        r = self.client.post(
            f"/t/{tenant_id}/setup/first-batch",
            headers=headers,
            json={"days": ["Sat"], "hour": 10, "name": "First"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get("batch_id") or r.json().get("batch"))

        st = self.client.get(f"/t/{tenant_id}/setup/status", headers=headers)
        self.assertEqual(st.status_code, 200)
        self.assertFalse(st.json()["needs_wizard"])
        self.assertGreaterEqual(st.json()["batch_count"], 1)

        again = self.client.post(
            f"/t/{tenant_id}/setup/first-batch",
            headers=headers,
            json={"days": ["Sun"], "hour": 11, "name": "Second"},
        )
        self.assertEqual(again.status_code, 409, again.text)
        self.assertIn("already has batches", again.json().get("detail", "").lower())


if __name__ == "__main__":
    unittest.main()
