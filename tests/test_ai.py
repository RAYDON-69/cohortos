"""
Portion 8 — AI Solve + Teach tests (SPEC Module 9 + ai-grounding-pipeline).
"""

from __future__ import annotations

import unittest
from services.app import create_app
from services.llm_provider import MockLLMProvider, GeminiProvider, RateLimitError, OfflineError
from services.ai_quota_service import QuotaExceededError
from models.ai import STATUS_APPROVED, STATUS_NEEDS_REVIEW, STATUS_REJECTED


class TestLLMProviders(unittest.TestCase):
    def test_mock_basic(self):
        llm = MockLLMProvider()
        from services.llm_provider import LLMRequest
        r = llm.complete(LLMRequest(prompt="What is force?", system="solve"))
        self.assertIn("ANSWER", r.text.upper())
        self.assertTrue(llm.is_available())

    def test_mock_rate_limit(self):
        llm = MockLLMProvider(force_rate_limit=True)
        from services.llm_provider import LLMRequest
        with self.assertRaises(RateLimitError):
            llm.complete(LLMRequest(prompt="x"))

    def test_mock_offline(self):
        llm = MockLLMProvider(force_offline=True)
        self.assertFalse(llm.is_available())
        from services.llm_provider import LLMRequest
        with self.assertRaises(OfflineError):
            llm.complete(LLMRequest(prompt="x"))

    def test_gemini_stub_degrades(self):
        g = GeminiProvider(api_key=None, online=False)
        self.assertFalse(g.is_available())
        from services.llm_provider import LLMRequest
        with self.assertRaises(OfflineError):
            g.complete(LLMRequest(prompt="x"))
        g2 = GeminiProvider(api_key="fake", online=True, force_rate_limit=True)
        with self.assertRaises(RateLimitError):
            g2.complete(LLMRequest(prompt="x"))


class TestSolvePipeline(unittest.TestCase):
    def setUp(self):
        self.app = create_app(llm=MockLLMProvider())
        self.summary = self.app.bootstrap_centre(create_sample_batches=True)
        self.batch = self.summary["batch_ids"][0]
        self.actor = self.summary["roles"]["owner"]
        self.sid, _ = self.app.admission.admit_student(
            name="AI Student",
            batch_id=self.batch,
            student_phone="01710000001",
            actor_id=self.actor,
        )
        # Seed vault resource for grounding
        self.res_id = self.app.content.create_resource(
            title="Newton Laws Notes",
            resource_type="pdf",
            topic="mechanics",
            subject="physics",
            description="Force equals mass times acceleration. Free body diagrams required.",
            batch_ids=[self.batch],
            actor_id=self.actor,
        )

    def test_grounded_solve(self):
        result = self.app.solve.ask(
            student_id=self.sid,
            question="Explain Newton's second law force motion",
            subject="physics",
            topic="mechanics",
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["grounded"])
        self.assertIn(self.res_id, result["source_chunk_ids"])
        self.assertTrue(result["answer"] or result["how"])
        self.assertFalse(result["needs_review"] or result.get("confidence", 1) < 0.5)

    def test_ungrounded_routes_to_review(self):
        result = self.app.solve.ask(
            student_id=self.sid,
            question="What is the capital of Atlantis underwater kingdom lore?",
            subject="history",
            topic="mythology",
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["grounded"])
        self.assertTrue(result["needs_review"])
        self.assertIn("ungrounded", (result.get("review_reason") or "").lower())

    def test_self_verification_mismatch(self):
        result = self.app.solve.ask(
            student_id=self.sid,
            question="__MISMATCH__ force calculation with sources mechanics newton",
            subject="physics",
            topic="mechanics",
        )
        self.assertTrue(result["ok"])
        # mismatch → needs review
        self.assertTrue(result["needs_review"] or result.get("verification_match") is False)

    def test_cache_hit(self):
        q = "Define velocity in mechanics physics notes"
        r1 = self.app.solve.ask(student_id=self.sid, question=q, subject="physics", topic="mechanics")
        self.assertTrue(r1["ok"])
        r2 = self.app.solve.ask(student_id=self.sid, question=q, subject="physics", topic="mechanics")
        self.assertTrue(r2["ok"])
        self.assertTrue(r2.get("cached"))

    def test_quota_enforced(self):
        self.app.ai_quota.set_caps(mcq=1, written=1)
        self.app.solve.ask(
            student_id=self.sid, question="q1 mechanics force", subject="physics", topic="mechanics"
        )
        r2 = self.app.solve.ask(
            student_id=self.sid, question="q2 mechanics force again", subject="physics", topic="mechanics"
        )
        self.assertFalse(r2["ok"])
        self.assertEqual(r2["error"], "quota_exceeded")

    def test_rate_limit_degrade(self):
        app = create_app(llm=MockLLMProvider(force_rate_limit=True))
        s = app.bootstrap_centre(create_sample_batches=False)
        bid = app.admission.create_batch(days=["mon"], hour=10)
        sid, _ = app.admission.admit_student(
            name="RL", batch_id=bid, student_phone="01710000002", actor_id=s["roles"]["owner"]
        )
        r = app.solve.ask(student_id=sid, question="anything", subject="physics")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "rate_limited")
        self.assertTrue(r["queued"])

    def test_offline_degrade(self):
        app = create_app(llm=MockLLMProvider(force_offline=True))
        s = app.bootstrap_centre(create_sample_batches=False)
        bid = app.admission.create_batch(days=["mon"], hour=10)
        sid, _ = app.admission.admit_student(
            name="Off", batch_id=bid, student_phone="01710000003", actor_id=s["roles"]["owner"]
        )
        r = app.solve.ask(student_id=sid, question="anything", subject="physics")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "offline")
        self.assertTrue(r["queued"])

    def test_thread_by_student_id(self):
        r = self.app.solve.ask(
            student_id=self.sid,
            question="force diagram mechanics",
            subject="physics",
            topic="mechanics",
        )
        threads = self.app.solve.list_threads(self.sid)
        self.assertGreaterEqual(len(threads), 1)
        msgs = self.app.solve.list_messages(r["thread_id"])
        self.assertGreaterEqual(len(msgs), 2)
        # annotate
        asst = [m for m in msgs if m["role"] == "assistant"][0]
        updated = self.app.solve.annotate_message(asst["id"], "Use my sign convention", self.actor)
        self.assertIn("sign", updated["teacher_annotation"])


class TestTeachPipeline(unittest.TestCase):
    def setUp(self):
        self.app = create_app(llm=MockLLMProvider())
        self.summary = self.app.bootstrap_centre(create_sample_batches=True)
        self.actor = self.summary["roles"]["owner"]
        self.batch = self.summary["batch_ids"][0]
        self.app.content.create_resource(
            title="Past Paper Torque",
            resource_type="pdf",
            topic="rotation",
            subject="physics",
            description="Torque equals force cross lever arm. Moment of inertia.",
            actor_id=self.actor,
        )

    def test_generate_never_auto_approved(self):
        item = self.app.teach.generate_item(
            item_type="mcq",
            subject="physics",
            topic="rotation",
            prompt="Generate 1 MCQ on torque",
            actor_id=self.actor,
        )
        self.assertNotEqual(item["status"], STATUS_APPROVED)
        self.assertEqual(item["status"], STATUS_NEEDS_REVIEW)
        visible = self.app.teach.student_visible_items(subject="physics")
        self.assertEqual(len(visible), 0)

    def test_review_gate_approve_reject(self):
        item = self.app.teach.generate_item(
            item_type="written",
            subject="physics",
            topic="rotation",
            prompt="written on moment of inertia",
            actor_id=self.actor,
        )
        approved = self.app.teach.approve_item(item["id"], actor_id=self.actor)
        self.assertEqual(approved["status"], STATUS_APPROVED)
        visible = self.app.teach.student_visible_items(subject="physics")
        self.assertEqual(len(visible), 1)

        item2 = self.app.teach.generate_item(
            item_type="mcq",
            subject="physics",
            topic="rotation",
            prompt="another mcq",
            actor_id=self.actor,
        )
        rejected = self.app.teach.reject_item(item2["id"], actor_id=self.actor, reason="off syllabus")
        self.assertEqual(rejected["status"], STATUS_REJECTED)
        # rejects retained
        all_items = self.app.data_layer.get_all("ai_generated_items")
        self.assertTrue(any(i["status"] == STATUS_REJECTED for i in all_items))

    def test_ungrounded_teach_flagged(self):
        item = self.app.teach.generate_item(
            item_type="mcq",
            subject="astrology",
            topic="zodiac",
            prompt="MCQ on star signs",
            actor_id=self.actor,
        )
        self.assertFalse(item["grounded"])
        self.assertEqual(item["status"], STATUS_NEEDS_REVIEW)
        self.assertIn("ungrounded", (item.get("review_reason") or "").lower())

    def test_style_profile_versioned(self):
        p1 = self.app.teach.upsert_style_profile(
            subject="physics",
            style_notes="Always show free-body diagram",
            sign_conventions="downward positive",
            actor_id=self.actor,
        )
        self.assertEqual(p1["version"], 1)
        p2 = self.app.teach.upsert_style_profile(
            subject="physics",
            style_notes="Always show free-body diagram; SI units only",
            actor_id=self.actor,
        )
        self.assertEqual(p2["version"], 2)

    def test_analytics_impact_ranking(self):
        a = self.app.teach.generate_analytics_suggestion(
            subject="physics", topic="rotation", cohort_size=5, weakness_severity=0.9, actor_id=self.actor
        )
        b = self.app.teach.generate_analytics_suggestion(
            subject="physics", topic="waves", cohort_size=1, weakness_severity=0.2, actor_id=self.actor
        )
        queue = self.app.teach.list_review_queue()
        # higher impact first
        self.assertGreaterEqual(queue[0]["impact_score"], queue[-1]["impact_score"])

    def test_push_to_exam_requires_approval(self):
        item = self.app.teach.generate_item(
            item_type="mcq", subject="physics", topic="rotation", prompt="mcq", actor_id=self.actor
        )
        with self.assertRaises(ValueError):
            self.app.teach.push_to_exam_bank(item["id"], actor_id=self.actor)
        self.app.teach.approve_item(item["id"], actor_id=self.actor)
        pushed = self.app.teach.push_to_exam_bank(item["id"], actor_id=self.actor)
        self.assertTrue(pushed["content"].get("pushed_to_exam_bank"))

    def test_ocr_stub(self):
        out = self.app.teach.ocr_grade_handwriting("img://scan1", actor_id=self.actor)
        self.assertFalse(out["ok"])
        self.assertIn("not implemented", out["message"].lower())


class TestAIAppIntegration(unittest.TestCase):
    def test_health_includes_ai(self):
        h = create_app().health()
        self.assertTrue(h["services"]["solve"])
        self.assertTrue(h["services"]["teach"])

    def test_tenant_isolation_threads(self):
        a1 = create_app()
        a2 = create_app()
        s1 = a1.bootstrap_centre(create_sample_batches=False)
        s2 = a2.bootstrap_centre(create_sample_batches=False)
        b1 = a1.admission.create_batch(days=["mon"], hour=9)
        b2 = a2.admission.create_batch(days=["mon"], hour=9)
        st1, _ = a1.admission.admit_student(name="T1", batch_id=b1, student_phone="01911111111", actor_id=s1["roles"]["owner"])
        st2, _ = a2.admission.admit_student(name="T2", batch_id=b2, student_phone="01922222222", actor_id=s2["roles"]["owner"])
        a1.solve.ask(student_id=st1, question="q", subject="physics")
        self.assertEqual(len(a1.solve.list_threads(st1)), 1)
        self.assertEqual(len(a2.solve.list_threads(st1)), 0)
        self.assertEqual(len(a2.solve.list_threads(st2)), 0)


if __name__ == "__main__":
    unittest.main()
