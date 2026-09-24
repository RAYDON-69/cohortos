"""Phase 12: payment providers sandbox/mock (no live merchant keys required)."""
from __future__ import annotations
import itertools
import os
import unittest

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")
# Ensure no accidental live keys
for k in list(os.environ):
    if k.startswith("COHORTOS_BKASH") or k.startswith("COHORTOS_NAGAD") or k.startswith("COHORTOS_STRIPE"):
        if "MODE" not in k:
            os.environ.pop(k, None)

from fastapi.testclient import TestClient
from api.main import create_api_app
from services.payment_providers.factory import get_payment_provider, list_providers
from services.payment_providers.base import ProviderError

_phone = itertools.count(1980001000)


class TestProvidersUnit(unittest.TestCase):
    def test_list_three(self):
        names = {p["name"] for p in list_providers()}
        self.assertEqual(names, {"bkash", "nagad", "stripe"})

    def test_bkash_mock_checkout_confirm(self):
        p = get_payment_provider("bkash")
        self.assertFalse(p.is_configured())
        sess = p.create_checkout(
            amount=5000, currency="BDT", invoice_id="inv-1", callback_url="http://localhost/cb"
        )
        self.assertTrue(sess.session_id.startswith("bkash_mock_"))
        self.assertEqual(sess.mode, "sandbox")
        res = p.confirm_payment(sess.session_id)
        self.assertTrue(res.success)
        self.assertTrue(res.transaction_id.startswith("MOCK-"))

    def test_nagad_mock(self):
        p = get_payment_provider("nagad")
        sess = p.create_checkout(
            amount=12000, currency="BDT", invoice_id="inv-2", callback_url="http://localhost/cb"
        )
        self.assertTrue(sess.session_id.startswith("nagad_mock_"))
        res = p.confirm_payment(sess.session_id)
        self.assertTrue(res.success)

    def test_stripe_mock(self):
        p = get_payment_provider("stripe")
        sess = p.create_checkout(
            amount=50, currency="USD", invoice_id="inv-3", callback_url="http://localhost/cb"
        )
        self.assertTrue(sess.session_id.startswith("stripe_mock_"))
        res = p.confirm_payment(sess.session_id)
        self.assertTrue(res.success)

    def test_bkash_rejects_non_bdt(self):
        p = get_payment_provider("bkash")
        with self.assertRaises(ProviderError):
            p.create_checkout(
                amount=10, currency="USD", invoice_id="x", callback_url="http://localhost/cb"
            )


class TestBillingPaymentAPI(unittest.TestCase):
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
            json={"centre_name": f"Pay{phone}", "owner_phone": phone, "owner_name": "O"},
        ).json()["tenant_id"]
        otp = self.client.post("/auth/request-otp", json={"phone": phone}).json()
        tok = self.client.post(
            "/auth/verify-otp",
            json={"otp_id": otp["otp_id"], "code": otp["_test_code"], "tenant_id": tid},
        ).json()
        return tid, {"Authorization": f"Bearer {tok['access_token']}"}

    def test_providers_endpoint(self):
        tid, h = self._login()
        r = self.client.get(f"/t/{tid}/billing/providers", headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        names = {p["name"] for p in r.json()["providers"]}
        self.assertEqual(names, {"bkash", "nagad", "stripe"})

    def test_checkout_confirm_bkash_mock_activates_sub(self):
        tid, h = self._login()
        r = self.client.post(
            f"/t/{tid}/billing/checkout",
            headers=h,
            json={"provider": "bkash", "amount": 5000, "currency": "BDT"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertFalse(body["provider_configured"])
        sid = body["checkout"]["session_id"]
        self.assertTrue(sid.startswith("bkash_mock_"))
        c = self.client.post(
            f"/t/{tid}/billing/confirm",
            headers=h,
            json={"provider": "bkash", "session_id": sid},
        )
        self.assertEqual(c.status_code, 200, c.text)
        self.assertTrue(c.json()["payment"]["success"])
        self.assertEqual(c.json()["subscription"]["status"], "active")
        self.assertEqual(c.json()["subscription"]["payment_provider"], "bkash")

    def test_checkout_stripe_mock(self):
        tid, h = self._login()
        r = self.client.post(
            f"/t/{tid}/billing/checkout",
            headers=h,
            json={"provider": "stripe", "amount": 29.0, "currency": "USD"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.json()["checkout"]["session_id"]
        c = self.client.post(
            f"/t/{tid}/billing/confirm",
            headers=h,
            json={"provider": "stripe", "session_id": sid},
        )
        self.assertEqual(c.status_code, 200)
        self.assertTrue(c.json()["payment"]["success"])

    def test_set_provider(self):
        tid, h = self._login()
        r = self.client.post(
            f"/t/{tid}/billing/provider",
            headers=h,
            json={"provider": "nagad"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["subscription"]["payment_provider"], "nagad")


if __name__ == "__main__":
    unittest.main()
