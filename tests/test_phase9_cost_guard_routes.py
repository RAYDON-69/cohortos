"""Phase 9: cost guard on solve (and query) routes."""
from __future__ import annotations
import itertools
import os
import unittest
from unittest import mock

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")

from fastapi.testclient import TestClient
from api.main import create_api_app

_phone = itertools.count(1960001000)


class TestCostGuardRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_api_app(
            jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
            cloud_db=":memory:",
            auth_db=":memory:",
            founder_token=os.environ["COHORTOS_FOUNDER_TOKEN"],
        )
        cls.client = TestClient(cls.app)

    def _login(self):
        n = next(_phone)
        phone = f"01{n:09d}"[-11:]
        tid = self.client.post(
            "/auth/centre-trial",
            json={"centre_name": f"CG{phone}", "owner_phone": phone, "owner_name": "O"},
        ).json()["tenant_id"]
        otp = self.client.post("/auth/request-otp", json={"phone": phone}).json()
        tok = self.client.post(
            "/auth/verify-otp",
            json={"otp_id": otp["otp_id"], "code": otp["_test_code"], "tenant_id": tid},
        ).json()
        return tid, {"Authorization": f"Bearer {tok['access_token']}"}

    def test_solve_ask_respects_cost_guard(self):
        tid, h = self._login()
        old = os.environ.get("COHORTOS_AI_MAX_CALLS_PER_WINDOW")
        os.environ["COHORTOS_AI_MAX_CALLS_PER_WINDOW"] = "2"
        try:
            # solve.ask may not need external LLM with mock — cost guard increments on entry
            r1 = self.client.post(
                f"/t/{tid}/solve/ask",
                headers=h,
                json={"student_id": "s1", "question": "What is force?", "subject": "physics"},
            )
            r2 = self.client.post(
                f"/t/{tid}/solve/ask",
                headers=h,
                json={"student_id": "s1", "question": "What is mass?", "subject": "physics"},
            )
            r3 = self.client.post(
                f"/t/{tid}/solve/ask",
                headers=h,
                json={"student_id": "s1", "question": "What is energy?", "subject": "physics"},
            )
            # first two may 200 or 400 from domain validation; third must be 429 if guard counted
            self.assertEqual(r3.status_code, 429, r3.text)
            self.assertIn("cost guard", r3.json().get("detail", "").lower())
        finally:
            if old is None:
                os.environ.pop("COHORTOS_AI_MAX_CALLS_PER_WINDOW", None)
            else:
                os.environ["COHORTOS_AI_MAX_CALLS_PER_WINDOW"] = old
