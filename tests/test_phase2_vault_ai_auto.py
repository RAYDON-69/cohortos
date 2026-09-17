"""Phase 2: vault upload open, automation run, AI grounded query."""
from __future__ import annotations
import base64
import itertools
import os
import unittest
os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")
from fastapi.testclient import TestClient
from api.main import create_api_app
_phone = itertools.count(1716666000)

class TestPhase2(unittest.TestCase):
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
        r = self.client.post("/auth/centre-trial", json={"centre_name": f"P2{phone}", "owner_phone": phone, "owner_name": "O"})
        self.assertEqual(r.status_code, 200, r.text)
        tid = r.json()["tenant_id"]
        otp = self.client.post("/auth/request-otp", json={"phone": phone}).json()
        tok = self.client.post("/auth/verify-otp", json={"otp_id": otp["otp_id"], "code": otp["_test_code"], "tenant_id": tid}).json()
        return tid, {"Authorization": f"Bearer {tok['access_token']}"}

    def test_vault_upload_and_download(self):
        tid, h = self._login()
        payload = base64.b64encode(b"hello-vault-phase2").decode()
        r = self.client.post(
            f"/t/{tid}/vault/upload",
            headers=h,
            json={"title": "Notes", "filename": "notes.txt", "content_base64": payload, "content_type": "text/plain"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["resource_id"]
        d = self.client.get(f"/t/{tid}/vault/{rid}/content", headers=h)
        self.assertEqual(d.status_code, 200, d.text)
        self.assertEqual(d.content, b"hello-vault-phase2")

    def test_ai_query_grounded(self):
        tid, h = self._login()
        r = self.client.post(f"/t/{tid}/ai/query", headers=h, json={"question": "How many students?"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("answer", body)
        self.assertIn("grounded", body)
        self.assertEqual(body["grounded"]["student_count"], 0)

    def test_automation_fee_reminders_runs(self):
        tid, h = self._login()
        r = self.client.post(f"/t/{tid}/automations/run-fee-reminders", headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["type"], "fee_reminder_escalation")
        self.assertIn("before", r.json())
        self.assertIn("after", r.json())

if __name__ == "__main__":
    unittest.main()
