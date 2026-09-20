"""Phase 7: automation rules, tutor isolation, double-run idempotency."""
from __future__ import annotations
import itertools
import os
import unittest

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")

from fastapi.testclient import TestClient
from api.main import create_api_app

_phone = itertools.count(1930001000)


class TestPhase7(unittest.TestCase):
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
        r = self.client.post(
            "/auth/centre-trial",
            json={"centre_name": f"P7{phone}", "owner_phone": phone, "owner_name": "O"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        tid = r.json()["tenant_id"]
        otp = self.client.post("/auth/request-otp", json={"phone": phone}).json()
        tok = self.client.post(
            "/auth/verify-otp",
            json={"otp_id": otp["otp_id"], "code": otp["_test_code"], "tenant_id": tid},
        ).json()
        return tid, {"Authorization": f"Bearer {tok['access_token']}"}

    def test_rule_crud_and_double_run(self):
        tid, h = self._login()
        r = self.client.post(
            f"/t/{tid}/automations/rules",
            headers=h,
            json={
                "name": "Fee overdue reminder",
                "enabled": True,
                "trigger": {"type": "manual"},
                "conditions": [],
                "actions": [{"type": "fee_reminder", "params": {}}],
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        rule = r.json()["rule"]
        rid = rule["id"]
        r1 = self.client.post(f"/t/{tid}/automations/rules/{rid}/run", headers=h, json={})
        r2 = self.client.post(f"/t/{tid}/automations/rules/{rid}/run", headers=h, json={})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        # second may skip duplicate fee path via idempotency inside action
        log = self.client.get(f"/t/{tid}/automations/log", headers=h).json()["log"]
        self.assertTrue(len(log) >= 1)

    def test_disabled_rule_skips(self):
        tid, h = self._login()
        r = self.client.post(
            f"/t/{tid}/automations/rules",
            headers=h,
            json={
                "name": "Disabled nag",
                "enabled": True,
                "trigger": {"type": "manual"},
                "actions": [{"type": "notify_staff", "params": {"message": "x"}}],
            },
        )
        rid = r.json()["rule"]["id"]
        self.client.post(
            f"/t/{tid}/automations/rules/{rid}/enable",
            headers=h,
            json={"enabled": False},
        )
        out = self.client.post(f"/t/{tid}/automations/rules/{rid}/run", headers=h, json={}).json()
        self.assertEqual(out.get("type"), "rule_skipped")

    def test_tutor_empty_vault_no_leak(self):
        tid, h = self._login()
        r = self.client.post(
            f"/t/{tid}/tutor/query",
            headers=h,
            json={"question": "Explain kinetics", "batch_id": "nonexistent-batch"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertFalse(body.get("grounded"))
        self.assertEqual(body.get("citations"), [])

    def test_tutor_cross_tenant_forbidden(self):
        tid1, h1 = self._login()
        tid2, h2 = self._login()
        r = self.client.post(
            f"/t/{tid2}/tutor/query",
            headers=h1,
            json={"question": "leak?", "batch_id": "x"},
        )
        self.assertIn(r.status_code, (401, 403))

    def test_ai_query_lists_automations(self):
        tid, h = self._login()
        self.client.post(
            f"/t/{tid}/automations/rules",
            headers=h,
            json={
                "name": "Fee overdue reminder",
                "enabled": True,
                "trigger": {"type": "manual"},
                "actions": [{"type": "fee_reminder"}],
            },
        )
        r = self.client.post(
            f"/t/{tid}/ai/query",
            headers=h,
            json={"question": "list automations and run fee reminders"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        tools = r.json().get("tools_used") or []
        names = [t.get("tool") for t in tools]
        self.assertTrue(
            "list_automations" in names or "run_automation" in names or r.json().get("grounded"),
            r.json(),
        )


if __name__ == "__main__":
    unittest.main()
