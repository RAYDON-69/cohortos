"""
Portion 10 — Multi-tenancy SaaS + Founder Super-Admin (SPEC Module 10).
"""

from __future__ import annotations

import unittest
from services.pricing_engine import PricingEngine, PricingError
from services.founder_admin import (
    FounderAdminService,
    FounderAuthError,
    TenantSuspendedError,
    TenantNotFoundError,
)
from services.app import create_app
from models.base import TenantContext, DataAccessLayer
import uuid


import os
TOKEN = os.environ.get("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-unit")


class TestPricingEngine(unittest.TestCase):
    def setUp(self):
        self.eng = PricingEngine()

    def test_starter_under_limit(self):
        q = self.eng.calculate(200)
        self.assertEqual(q["tier"], "starter")
        self.assertEqual(q["base_price_bdt"], 5000)
        self.assertEqual(q["overage_students"], 0)
        self.assertEqual(q["amount_due_bdt"], 5000)

    def test_growth_boundary(self):
        q = self.eng.calculate(501)
        self.assertEqual(q["tier"], "growth")
        self.assertEqual(q["base_price_bdt"], 12000)

    def test_overage(self):
        # force starter tier with students above limit
        q = self.eng.calculate(520, tier="starter", overage_rate=15)
        self.assertEqual(q["overage_students"], 20)
        self.assertEqual(q["overage_amount_bdt"], 300)
        self.assertEqual(q["monthly_total_bdt"], 5300)

    def test_annual_discount(self):
        q = self.eng.calculate(100, billing_cycle="annual", annual_discount=0.15)
        self.assertEqual(q["billing_cycle"], "annual")
        expected = round(5000 * 12 * 0.85, 2)
        self.assertEqual(q["amount_due_bdt"], expected)

    def test_scale_limit_exceeded(self):
        with self.assertRaises(PricingError):
            self.eng.calculate(6001)

    def test_recommend_tiers(self):
        self.assertEqual(self.eng.recommend_tier(10), "starter")
        self.assertEqual(self.eng.recommend_tier(1000), "growth")
        self.assertEqual(self.eng.recommend_tier(3000), "scale")


class TestFounderAdmin(unittest.TestCase):
    def setUp(self):
        self.admin = FounderAdminService(founder_token=TOKEN)

    def test_auth_required(self):
        with self.assertRaises(FounderAuthError):
            self.admin.list_tenants("bad-token")

    def test_provision_and_list(self):
        t = self.admin.provision_tenant(
            name="Barishal Physics",
            code="BAR-PHY",
            founder_token=TOKEN,
            student_count=400,
        )
        self.assertEqual(t["status"], "trial")
        self.assertEqual(t["tier"], "starter")
        listed = self.admin.list_tenants(TOKEN)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["code"], "BAR-PHY")

    def test_duplicate_code_rejected(self):
        self.admin.provision_tenant(name="A", code="DUP", founder_token=TOKEN)
        with self.assertRaises(ValueError):
            self.admin.provision_tenant(name="B", code="DUP", founder_token=TOKEN)

    def test_suspend_and_assert(self):
        t = self.admin.provision_tenant(name="X", code="SUS1", founder_token=TOKEN)
        self.admin.activate_tenant(t["id"], TOKEN)
        self.admin.suspend_tenant(t["id"], TOKEN, reason="non-payment")
        with self.assertRaises(TenantSuspendedError):
            self.admin.assert_tenant_active(t["id"])

    def test_extend_reactivates(self):
        t = self.admin.provision_tenant(name="Y", code="EXT1", founder_token=TOKEN)
        self.admin.suspend_tenant(t["id"], TOKEN, reason="hold")
        extended = self.admin.extend_tenant(t["id"], TOKEN, days=30)
        self.assertEqual(extended["status"], "active")
        self.assertTrue(extended.get("extended_until"))
        self.admin.assert_tenant_active(t["id"])  # should not raise

    def test_update_student_count_retiers(self):
        t = self.admin.provision_tenant(
            name="Z", code="TIER1", founder_token=TOKEN, student_count=100
        )
        self.assertEqual(t["tier"], "starter")
        updated = self.admin.update_student_count(t["id"], 800, TOKEN)
        self.assertEqual(updated["tier"], "growth")

    def test_byok_fingerprint_no_raw_in_record(self):
        t = self.admin.provision_tenant(name="K", code="KEY1", founder_token=TOKEN)
        out = self.admin.set_gemini_key(t["id"], "sk-secret-value-abc", TOKEN)
        self.assertTrue(out["gemini_key_present"])
        stored = self.admin.get_tenant(t["id"])
        self.assertTrue(stored["gemini_key_present"])
        self.assertTrue(stored["gemini_key_fingerprint"])
        self.assertNotIn("sk-secret", str(stored))
        raw = self.admin.get_gemini_key(t["id"], TOKEN)
        self.assertEqual(raw, "sk-secret-value-abc")
        self.admin.clear_gemini_key(t["id"], TOKEN)
        self.assertFalse(self.admin.get_tenant(t["id"])["gemini_key_present"])

    def test_ai_metrics_no_spend(self):
        t = self.admin.provision_tenant(name="M", code="MET1", founder_token=TOKEN)
        self.admin.record_ai_event(t["id"], query=True, written=True)
        self.admin.record_ai_event(t["id"], query=True, mcq=True, cache_hit=True)
        self.admin.record_ai_event(t["id"], rate_limit=True, cache_miss=True)
        m = self.admin.get_ai_metrics(t["id"], TOKEN)
        self.assertEqual(m["query_volume"], 2)
        self.assertEqual(m["mcq_count"], 1)
        self.assertEqual(m["written_count"], 1)
        self.assertEqual(m["rate_limit_hits"], 1)
        self.assertAlmostEqual(m["cache_hit_rate"], 0.5)
        self.assertNotIn("spend", m)
        self.assertNotIn("gemini_cost", m)
        self.assertNotIn("cost_usd", m)

    def test_dashboard(self):
        self.admin.provision_tenant(name="D1", code="DASH1", founder_token=TOKEN)
        self.admin.provision_tenant(name="D2", code="DASH2", founder_token=TOKEN, student_count=600)
        dash = self.admin.dashboard(TOKEN)
        self.assertEqual(dash["tenant_count"], 2)
        self.assertEqual(len(dash["tenants"]), 2)
        # metrics keys present, no spend
        for s in dash["tenants"]:
            self.assertIn("query_volume", s["metrics"])
            self.assertNotIn("spend", s["metrics"])

    def test_billing_status(self):
        t = self.admin.provision_tenant(
            name="Bill", code="BILL1", founder_token=TOKEN, student_count=520
        )
        # 520 → growth recommended on provision; force count update path already set
        bill = self.admin.billing_status(t["id"], TOKEN)
        self.assertIn("quote", bill)
        self.assertEqual(bill["quote"]["currency"], "BDT")
        self.assertNotIn("spend", bill)

    def test_audit_trail(self):
        t = self.admin.provision_tenant(name="Aud", code="AUD1", founder_token=TOKEN)
        self.admin.suspend_tenant(t["id"], TOKEN, reason="test")
        audit = self.admin.list_audit(TOKEN)
        actions = [a["action"] for a in audit]
        self.assertIn("provision", actions)
        self.assertIn("suspend", actions)

    def test_quote_public_without_token_ok(self):
        # quote may be used pre-login for marketing
        q = self.admin.quote(300)
        self.assertEqual(q["tier"], "starter")


class TestTenantIsolationWithSaaS(unittest.TestCase):
    """Centre apps remain isolated; founder is separate control plane."""

    def test_two_centres_cannot_see_each_other(self):
        app1 = create_app()
        app2 = create_app()
        s1 = app1.bootstrap_centre(name="Centre1", code="C1", create_sample_batches=False)
        s2 = app2.bootstrap_centre(name="Centre2", code="C2", create_sample_batches=False)
        centres1 = app1.data.get_all_centres()
        centres2 = app2.data.get_all_centres()
        self.assertEqual(len(centres1), 1)
        self.assertEqual(len(centres2), 1)
        self.assertNotEqual(centres1[0]["id"], centres2[0]["id"])
        # Cross-get returns nothing
        self.assertIsNone(app2.data.get_centre(uuid.UUID(centres1[0]["id"])))

    def test_founder_not_centre_owner(self):
        admin = FounderAdminService(founder_token=TOKEN)
        t = admin.provision_tenant(name="Iso", code="ISO1", founder_token=TOKEN)
        # Centre owner path has no access to founder methods without token
        with self.assertRaises(FounderAuthError):
            admin.list_tenants(founder_token="")


if __name__ == "__main__":
    unittest.main()
