"""Stress: refresh token survives 10 sequential rotations (app relaunch simulation)."""
from __future__ import annotations
import itertools
import os
import unittest
os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")
from fastapi.testclient import TestClient
from api.main import create_api_app
_phone = itertools.count(1715555000)

class TestSessionRelaunch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_api_app(
            jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
            cloud_db=":memory:",
            auth_db=":memory:",
            founder_token=os.environ["COHORTOS_FOUNDER_TOKEN"],
        )
        cls.client = TestClient(cls.app)

    def test_refresh_ten_times_without_otp(self):
        n = next(_phone)
        phone = f"01{n:09d}"[-11:]
        r = self.client.post("/auth/centre-trial", json={"centre_name": f"S{phone}", "owner_phone": phone, "owner_name": "O"})
        self.assertEqual(r.status_code, 200, r.text)
        tid = r.json()["tenant_id"]
        otp = self.client.post("/auth/request-otp", json={"phone": phone}).json()
        self.assertIn("_test_code", otp)
        tok = self.client.post("/auth/verify-otp", json={"otp_id": otp["otp_id"], "code": otp["_test_code"], "tenant_id": tid}).json()
        rt = tok["refresh_token"]
        for i in range(10):
            r = self.client.post("/auth/refresh", json={"refresh_token": rt})
            self.assertEqual(r.status_code, 200, f"relaunch {i+1}: {r.text}")
            rt = r.json()["refresh_token"]
            self.assertTrue(r.json().get("access_token"))

if __name__ == "__main__":
    unittest.main()
