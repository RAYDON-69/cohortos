"""Product definition tests: self-serve trial, phone-only login, no tenant-id friction."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")
os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")

from fastapi.testclient import TestClient
from api.main import create_api_app


class TestCentreTrialOnboarding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_api_app(
            jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
            cloud_db=":memory:",
            auth_db=":memory:",
            founder_token=os.environ["COHORTOS_FOUNDER_TOKEN"],
        )
        cls.client = TestClient(cls.app)

    def test_trial_creates_centre_without_founder_token(self):
        r = self.client.post(
            "/auth/centre-trial",
            json={
                "centre_name": "Barishal Physics",
                "owner_phone": "01710000001",
                "owner_name": "Owner",
                "student_count": 100,
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("tenant_id", data)
        self.assertIn("centre_code", data)
        self.assertIn("trial_ends_at", data)
        self.assertIn("account_id", data)

    def test_trial_rejects_invalid_input(self):
        r = self.client.post(
            "/auth/centre-trial",
            json={"centre_name": "", "owner_phone": "01710000002"},
        )
        self.assertEqual(r.status_code, 400)
        r = self.client.post(
            "/auth/centre-trial",
            json={"centre_name": "X", "owner_phone": "12"},
        )
        self.assertEqual(r.status_code, 400)

    def test_phone_only_otp_and_owner_login(self):
        r = self.client.post(
            "/auth/centre-trial",
            json={
                "centre_name": "OTP Centre",
                "owner_phone": "01710000003",
                "owner_name": "Owner",
            },
        )
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/auth/request-otp", json={"phone": "01710000003"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("otp_id"))
        self.assertTrue(r.json().get("tenant_id"))
        self.assertTrue(r.json().get("_test_code"))
        r2 = self.client.post(
            "/auth/verify-otp",
            json={
                "otp_id": r.json()["otp_id"],
                "code": r.json()["_test_code"],
                "tenant_id": r.json()["tenant_id"],
            },
        )
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json().get("access_token"))
        self.assertIn("owner", r2.json().get("roles") or [])

    def test_unknown_phone_no_leak(self):
        r = self.client.post("/auth/request-otp", json={"phone": "01999999998"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json().get("otp_id"))

    def test_desk_batch_and_manual_admit(self):
        r = self.client.post(
            "/auth/centre-trial",
            json={
                "centre_name": "Desk Centre",
                "owner_phone": "01710000004",
                "owner_name": "Owner",
            },
        )
        tid = r.json()["tenant_id"]
        r = self.client.post("/auth/request-otp", json={"phone": "01710000004"})
        r2 = self.client.post(
            "/auth/verify-otp",
            json={
                "otp_id": r.json()["otp_id"],
                "code": r.json()["_test_code"],
                "tenant_id": r.json()["tenant_id"],
            },
        )
        h = {"Authorization": f"Bearer {r2.json()['access_token']}"}
        r = self.client.post(
            f"/t/{tid}/batches",
            json={"days": ["Sat", "Mon"], "hour": 10, "name": "Batch A"},
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        bid = r.json().get("batch_id") or (r.json().get("batch") or {}).get("id")
        self.assertTrue(bid)
        r = self.client.post(
            f"/t/{tid}/students",
            json={
                "name": "Student One",
                "batch_id": bid,
                "phone": "01720000011",
                "parent_phone": "01820000011",
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        # Sibling same parent phone
        r = self.client.post(
            f"/t/{tid}/students",
            json={
                "name": "Student Two",
                "batch_id": bid,
                "phone": "01720000012",
                "parent_phone": "01820000011",
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        # Duplicate student phone
        r = self.client.post(
            f"/t/{tid}/students",
            json={"name": "Dup", "batch_id": bid, "phone": "01720000011"},
            headers=h,
        )
        self.assertIn(r.status_code, (400, 409))

    def test_unauthenticated_desk_blocked(self):
        r = self.client.get("/t/00000000-0000-4000-8000-000000000001/students")
        self.assertIn(r.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
