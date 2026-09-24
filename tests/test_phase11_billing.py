"""Phase 11: billing data model + usage meter API (no live payments)."""
from __future__ import annotations
import itertools
import os
import unittest

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")

from fastapi.testclient import TestClient
from api.main import create_api_app
from models.billing import BillingPlan, Subscription, UsageLineItem, Invoice, DEFAULT_PLANS
from services.billing_service import BillingService

_phone = itertools.count(1970001000)


class TestBillingModels(unittest.TestCase):
    def test_default_plans_three(self):
        self.assertEqual(len(DEFAULT_PLANS), 3)
        codes = {p.code for p in DEFAULT_PLANS}
        self.assertEqual(codes, {"starter", "growth", "scale"})

    def test_roundtrip_dicts(self):
        p = DEFAULT_PLANS[0]
        self.assertEqual(BillingPlan.from_dict(p.to_dict()).code, p.code)
        s = Subscription(tenant_id="t1", plan_code="starter")
        self.assertEqual(Subscription.from_dict(s.to_dict()).tenant_id, "t1")
        u = UsageLineItem(tenant_id="t1", provider="groq", route="ai/query")
        self.assertEqual(UsageLineItem.from_dict(u.to_dict()).provider, "groq")
        inv = Invoice(tenant_id="t1", total=5000)
        self.assertEqual(Invoice.from_dict(inv.to_dict()).total, 5000)


class TestBillingAPI(unittest.TestCase):
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
            json={"centre_name": f"Bill{phone}", "owner_phone": phone, "owner_name": "O"},
        ).json()["tenant_id"]
        otp = self.client.post("/auth/request-otp", json={"phone": phone}).json()
        tok = self.client.post(
            "/auth/verify-otp",
            json={"otp_id": otp["otp_id"], "code": otp["_test_code"], "tenant_id": tid},
        ).json()
        return tid, {"Authorization": f"Bearer {tok['access_token']}"}

    def test_usage_empty_then_after_guard(self):
        tid, h = self._login()
        r = self.client.get(f"/t/{tid}/billing/usage", headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["total_calls"], 0)
        self.assertIn("by_provider", body)
        self.assertEqual(body.get("payment_provider"), "none")

        # Record via solve cost guard
        self.client.post(
            f"/t/{tid}/solve/ask",
            headers=h,
            json={"student_id": "s1", "question": "What is force?", "subject": "physics"},
        )
        r2 = self.client.get(f"/t/{tid}/billing/usage", headers=h)
        self.assertEqual(r2.status_code, 200)
        self.assertGreaterEqual(r2.json()["total_calls"], 1)

    def test_subscription_and_plans(self):
        tid, h = self._login()
        r = self.client.get(f"/t/{tid}/billing/subscription", headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("subscription", body)
        self.assertGreaterEqual(len(body.get("plans") or []), 3)
        self.assertEqual(body["subscription"].get("payment_provider"), "none")

    def test_draft_invoice(self):
        tid, h = self._login()
        r = self.client.post(f"/t/{tid}/billing/invoices/draft", headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        inv = r.json()
        self.assertEqual(inv.get("status"), "draft")
        self.assertGreater(float(inv.get("total") or 0), 0)


if __name__ == "__main__":
    unittest.main()
