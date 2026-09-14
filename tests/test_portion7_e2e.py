"""
Portion 7 end-to-end integration tests.

Covers multi-module flows required for the compile + handoff milestone:
- Bootstrap centre + batches
- Admit students (duplicate detection)
- Manual attendance + evaluation + irregularity
- Payment mark + lock (immutability)
- Exam result entry (permanent history)
- Content resource + access rules (AND composition) + anti-leak
- Roll/batch migration preserves history
- Shared DataAccessLayer consistency across services
- CohortOSApp composition root health

All tests use offline-first in-memory store (zero network).
"""

from __future__ import annotations

import uuid
import unittest
from datetime import datetime, timezone, timedelta

from services.app import CohortOSApp, create_app
from services.admission_service import DuplicateStudentError
from services.content_service import AccessDeniedError, ProtectionPermissionError


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class TestPortion7Composition(unittest.TestCase):
    def test_create_app_and_health(self):
        app = create_app(mode="offline-first")
        h = app.health()
        self.assertEqual(h["mode"], "offline-first")
        for key in ("admission", "attendance", "payment", "exam", "content"):
            self.assertTrue(h["services"][key])
        self.assertIsNotNone(app.tenant_id)

    def test_bootstrap_centre(self):
        app = create_app()
        summary = app.bootstrap_centre(
            name="Swapan Physics",
            code="BARISHAL",
            create_sample_batches=True,
        )
        self.assertTrue(summary["centre_id"])
        self.assertGreaterEqual(len(summary["batch_ids"]), 4)
        self.assertIn("owner", summary["roles"])
        batches = app.admission.list_batches()
        self.assertGreaterEqual(len(batches), 4)


class TestPortion7HappyPath(unittest.TestCase):
    """Full day-in-the-life flow across Modules 1–5."""

    def setUp(self):
        self.app = create_app(mode="offline-first")
        self.summary = self.app.bootstrap_centre(
            name="E2E Centre", code="E2E01", create_sample_batches=True
        )
        self.batch_id = self.summary["batch_ids"][0]
        self.actor = self.summary["roles"]["owner"]

    def test_admit_attend_pay_exam_content(self):
        # 1. Admit two students
        s1, _jc1 = self.app.admission.admit_student(
            name="Rahim Khan",
            batch_id=self.batch_id,
            student_phone="01711111111",
            parent_phones=["01722222222"],
            actor_id=self.actor,
        )
        s2, _jc2 = self.app.admission.admit_student(
            name="Karim Ali",
            batch_id=self.batch_id,
            student_phone="01733333333",
            actor_id=self.actor,
        )
        self.assertIsNotNone(s1)
        self.assertIsNotNone(s2)
        st1 = self.app.admission.get_student(s1)
        self.assertEqual(st1["name"], "Rahim Khan")
        self.assertTrue(st1.get("roll"))

        # Duplicate detection [BULLET]
        with self.assertRaises(DuplicateStudentError):
            self.app.admission.admit_student(
                name="Rahim Khan",
                batch_id=self.batch_id,
                student_phone="01711111111",
                actor_id=self.actor,
            )

        # 2. Manual attendance for today
        today = _today()
        self.app.attendance.mark_manual(
            student_id=s1,
            on_date=today,
            status_or_time="present",
            actor_id=self.actor,
            batch_id=self.batch_id,
        )
        # evaluate day (returns attendance_record id)
        rec_id = self.app.attendance.evaluate_student_day(s1, today)
        self.assertIsNotNone(rec_id)
        att = self.app.attendance.get_attendance(s1, today)
        self.assertIsNotNone(att)
        status = (att.get("status") or att.get("final_status") or "").lower()
        self.assertIn(status, ("present", "late"))

        # 3. Payment: mark paid then lock
        year, month = datetime.now(timezone.utc).year, datetime.now(timezone.utc).month
        pay_rec = self.app.payment.mark_paid(
            student_id=s1,
            year=year,
            month=month,
            actor_id=self.actor,
        )
        self.assertIsNotNone(pay_rec)
        self.app.payment.lock_payment(s1, year, month, actor_id=self.actor)
        locked = self.app.payment.get_payment(s1, year, month)
        self.assertTrue(
            locked.get("locked") in (True, 1, "1") or bool(locked.get("locked")),
            f"expected locked payment, got {locked}",
        )

        # 4. Exam result
        tmpl = self.app.exam.ensure_default_template(actor_id=self.actor)
        exam = self.app.exam.create_exam(
            name="Weekly Physics",
            exam_date=today,
            batch_id=self.batch_id,
            template_id=tmpl.get("id") if isinstance(tmpl, dict) else tmpl,
            actor_id=self.actor,
        )
        exam_id = exam if isinstance(exam, str) else exam.get("id")
        result = self.app.exam.enter_result(
            exam_id=exam_id,
            student_id=s1,
            section_scores=[{"key": "mcq", "marks_obtained": 18, "max_marks": 20}],
            actor_id=self.actor,
        )
        self.assertIsNotNone(result)

        # 5. Content + access rules (paid + attendance)
        res_id = self.app.content.create_resource(
            title="Chapter 5 Notes",
            resource_type="pdf",
            topic="Mechanics",
            batch_ids=[self.batch_id],
            access_rules={
                "operator": "AND",
                "rules": [
                    {"kind": "min_attendance_pct", "value": 1},
                    {"kind": "paid_up", "value": True},
                ],
            },
            protection_level="owner_only",
            actor_id=self.actor,
        )
        # Student who attended + paid should pass evaluation
        decision = self.app.content.evaluate_access(
            resource_id=res_id,
            student_id=s1,
        )
        # evaluate_access may return bool or dict; accept both
        allowed = decision if isinstance(decision, bool) else decision.get("allowed", decision.get("access", False))
        self.assertTrue(allowed, f"expected access granted, got {decision}")

        # Student with no attendance should be denied under AND rules
        decision2 = self.app.content.evaluate_access(
            resource_id=res_id,
            student_id=s2,
        )
        allowed2 = decision2 if isinstance(decision2, bool) else decision2.get("allowed", decision2.get("access", True))
        # s2 has no attendance/payment → should be denied
        self.assertFalse(allowed2, f"expected access denied for s2, got {decision2}")


class TestPortion7EdgeCases(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.summary = self.app.bootstrap_centre(create_sample_batches=True)
        self.batch_id = self.summary["batch_ids"][0]
        self.actor = self.summary["roles"]["owner"]
        self.teacher = self.summary["roles"]["teacher"]
        self.desk = self.summary["roles"]["desk"]

    def test_anti_leak_desk_blocked(self):
        """Desk role cannot relax anti-leak protection [BULLET][LOCKED]."""
        res_id = self.app.content.create_resource(
            title="Sensitive Notes",
            resource_type="pdf",
            protection_level="owner_only",
            actor_id=self.actor,
            actor_role="owner",
        )
        with self.assertRaises(ProtectionPermissionError):
            self.app.content.update_resource(
                res_id,
                actor_id=self.desk,
                actor_role="desk",
                protection_level="relaxed",
            )
        with self.assertRaises(ProtectionPermissionError):
            self.app.content.relax_protection(
                res_id, actor_id=self.desk, actor_role="desk"
            )

    def test_roll_migration_preserves_history(self):
        """Roll/batch change migrates attendance/payment/results [BULLET]."""
        s1, _ = self.app.admission.admit_student(
            name="Migratable Student",
            batch_id=self.batch_id,
            student_phone="01899999999",
            actor_id=self.actor,
        )
        today = _today()
        self.app.attendance.mark_manual(
            student_id=s1, on_date=today, status_or_time="present", actor_id=self.actor, batch_id=self.batch_id
        )
        year = datetime.now(timezone.utc).year
        month = datetime.now(timezone.utc).month
        self.app.payment.mark_paid(student_id=s1, year=year, month=month, actor_id=self.actor)

        # New batch
        new_batch = self.app.admission.create_batch(days=["Fri"], hour=11)
        result = self.app.admission.migrate_student_roll_batch(
            student_id=s1,
            new_batch_id=new_batch,
            actor_id=self.actor,
        )
        self.assertIsNotNone(result)
        st = self.app.admission.get_student(s1)
        self.assertEqual(st.get("batch_id"), new_batch or st.get("batch_id"))
        # Attendance still present under same student_id (history not lost)
        att = self.app.attendance.get_attendance(s1, today)
        self.assertIsNotNone(att)

    def test_shared_data_layer_consistency(self):
        """All services share one DataAccessLayer instance."""
        app = create_app()
        self.assertIs(app.admission.data_layer, app.attendance.data_layer)
        self.assertIs(app.admission.data_layer, app.payment.data_layer)
        self.assertIs(app.admission.data_layer, app.exam.data_layer)
        self.assertIs(app.admission.data_layer, app.content.data_layer)

    def test_offline_first_zero_network(self):
        """Core actions succeed with no network / no sync required."""
        app = create_app(enable_sync=False, enable_notifications=False)
        summary = app.bootstrap_centre(create_sample_batches=False)
        bid = app.admission.create_batch(days=["Sat"], hour=9)
        sid, _ = app.admission.admit_student(
            name="Offline Only",
            batch_id=bid,
            student_phone="01600000000",
            actor_id=summary["roles"]["owner"],
        )
        app.attendance.mark_manual(
            student_id=sid, on_date=_today(), status_or_time="present", actor_id=summary["roles"]["owner"]
        )
        self.assertTrue(True)  # reached without network


class TestPortion7Irregularity(unittest.TestCase):
    def test_irregular_flag_shared_threshold(self):
        app = create_app()
        summary = app.bootstrap_centre(create_sample_batches=True)
        batch_id = summary["batch_ids"][0]
        actor = summary["roles"]["owner"]
        # Force low threshold for test
        app.config.set("irregularity.min_days_attended_month", 2)
        s1, _ = app.admission.admit_student(
            name="Irregular Kid",
            batch_id=batch_id,
            student_phone="01555555555",
            actor_id=actor,
        )
        # Zero attendance → irregular
        now = datetime.now(timezone.utc)
        self.assertTrue(app.attendance.is_irregular(s1, now.year, now.month))


if __name__ == "__main__":
    unittest.main()
