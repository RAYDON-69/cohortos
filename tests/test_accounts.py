"""
Portion 9 — Student & Parent Accounts (SPEC Module 8 [LOCKED]).
"""

from __future__ import annotations

import unittest
from services.app import create_app
from services.account_service import (
    AccountService,
    AccessDeniedError,
    DuplicateAccountError,
    AccountError,
)
from services.llm_provider import MockLLMProvider


class TestAccountSignupAndDedup(unittest.TestCase):
    def setUp(self):
        self.app = create_app(llm=MockLLMProvider())
        self.summary = self.app.bootstrap_centre(create_sample_batches=True)
        self.actor = self.summary["roles"]["owner"]
        self.batch = self.summary["batch_ids"][0]

    def test_create_student_account(self):
        acct = self.app.accounts.create_account(
            role="student", phone="01711110001", display_name="Rahim"
        )
        self.assertTrue(acct["id"])
        self.assertEqual(acct["phone"], "01711110001")
        self.assertFalse(self.app.accounts.is_linked(acct["id"]))

    def test_duplicate_phone_rejected(self):
        self.app.accounts.create_account(phone="01711110002")
        with self.assertRaises(DuplicateAccountError):
            self.app.accounts.create_account(phone="01711110002")

    def test_identifier_mode_phone_only(self):
        self.app.accounts.set_identifier_mode("phone")
        with self.assertRaises(AccountError):
            self.app.accounts.create_account(email="only@x.com")
        ok = self.app.accounts.create_account(phone="01711110003")
        self.assertTrue(ok["id"])


class TestJoinAndLink(unittest.TestCase):
    def setUp(self):
        self.app = create_app(llm=MockLLMProvider())
        self.summary = self.app.bootstrap_centre(create_sample_batches=True)
        self.actor = self.summary["roles"]["owner"]
        self.batch = self.summary["batch_ids"][0]
        self.sid, self.join_code = self.app.admission.admit_student(
            name="Karim Ali",
            batch_id=self.batch,
            student_phone="01722220001",
            actor_id=self.actor,
        )
        self.acct = self.app.accounts.create_account(
            phone="01733330001", display_name="Karim App"
        )

    def test_link_via_join_code(self):
        result = self.app.accounts.link(
            admission_id=self.sid,
            cohortos_account_id=self.acct["id"],
            join_code=self.join_code,
            actor_id=self.actor,
        )
        self.assertTrue(result["linked"])
        self.assertTrue(self.app.accounts.is_linked(self.acct["id"]))
        student = self.app.admission.get_student(self.sid)
        self.assertEqual(student["cohortos_account_id"], self.acct["id"])

    def test_join_code_single_use(self):
        self.app.accounts.link(
            admission_id=self.sid,
            cohortos_account_id=self.acct["id"],
            join_code=self.join_code,
            actor_id=self.actor,
        )
        acct2 = self.app.accounts.create_account(phone="01733330002")
        with self.assertRaises(Exception):
            self.app.accounts.link(
                admission_id=self.sid,
                cohortos_account_id=acct2["id"],
                join_code=self.join_code,
                actor_id=self.actor,
            )

    def test_staff_manual_link_with_confirm(self):
        # fresh student
        sid2, _ = self.app.admission.admit_student(
            name="Staff Link Student",
            batch_id=self.batch,
            student_phone="01722220002",
            actor_id=self.actor,
        )
        acct2 = self.app.accounts.create_account(phone="01733330003")
        result = self.app.accounts.link(
            admission_id=sid2,
            cohortos_account_id=acct2["id"],
            join_code=None,  # staff path
            actor_id=self.actor,
            confirm_name="Staff Link Student",
        )
        self.assertTrue(result["linked"])

    def test_confirm_name_mismatch(self):
        sid2, _ = self.app.admission.admit_student(
            name="Real Name",
            batch_id=self.batch,
            student_phone="01722220003",
            actor_id=self.actor,
        )
        acct2 = self.app.accounts.create_account(phone="01733330004")
        with self.assertRaises(AccountError):
            self.app.accounts.link(
                admission_id=sid2,
                cohortos_account_id=acct2["id"],
                actor_id=self.actor,
                confirm_name="Wrong Name",
            )

    def test_unlink(self):
        self.app.accounts.link(
            admission_id=self.sid,
            cohortos_account_id=self.acct["id"],
            join_code=self.join_code,
            actor_id=self.actor,
        )
        out = self.app.accounts.unlink(self.sid, actor_id=self.actor)
        self.assertTrue(out["unlinked"])
        self.assertFalse(self.app.accounts.is_linked(self.acct["id"]))
        # admission data preserved
        st = self.app.admission.get_student(self.sid)
        self.assertEqual(st["name"], "Karim Ali")

    def test_regenerate_invalidates_old(self):
        new_code = self.app.accounts.regenerate_join_code(self.sid, actor_id=self.actor)
        self.assertNotEqual(new_code, self.join_code)
        with self.assertRaises(Exception):
            self.app.accounts.link(
                admission_id=self.sid,
                cohortos_account_id=self.acct["id"],
                join_code=self.join_code,
                actor_id=self.actor,
            )
        result = self.app.accounts.link(
            admission_id=self.sid,
            cohortos_account_id=self.acct["id"],
            join_code=new_code,
            actor_id=self.actor,
        )
        self.assertTrue(result["linked"])


class TestZeroAccessUnlinked(unittest.TestCase):
    def setUp(self):
        self.app = create_app(llm=MockLLMProvider())
        self.summary = self.app.bootstrap_centre(create_sample_batches=True)
        self.actor = self.summary["roles"]["owner"]
        self.batch = self.summary["batch_ids"][0]
        self.acct = self.app.accounts.create_account(phone="01744440001")

    def test_unlinked_cannot_view(self):
        with self.assertRaises(AccessDeniedError):
            self.app.accounts.student_view(self.acct["id"])

    def test_linked_can_view(self):
        sid, code = self.app.admission.admit_student(
            name="View Student",
            batch_id=self.batch,
            student_phone="01744440002",
            actor_id=self.actor,
        )
        self.app.accounts.link(
            admission_id=sid,
            cohortos_account_id=self.acct["id"],
            join_code=code,
            actor_id=self.actor,
        )
        view = self.app.accounts.student_view(self.acct["id"])
        self.assertEqual(view["admission_id"], sid)
        self.assertEqual(view["student"]["name"], "View Student")


class TestOTPLogin(unittest.TestCase):
    def setUp(self):
        self.app = create_app(llm=MockLLMProvider())
        self.app.bootstrap_centre(create_sample_batches=False)
        self.acct = self.app.accounts.create_account(phone="01755550001")

    def test_otp_flow(self):
        sent = self.app.accounts.request_login_otp(phone="01755550001")
        self.assertTrue(sent["sent"])
        self.assertTrue(sent.get("otp_id"))
        code = sent["_test_code"]
        session = self.app.accounts.verify_login_otp(sent["otp_id"], code)
        self.assertTrue(session["session_token"])
        self.assertEqual(session["account_id"], self.acct["id"])
        resolved = self.app.accounts.resolve_session(session["session_token"])
        self.assertEqual(resolved["id"], self.acct["id"])

    def test_otp_wrong_code(self):
        sent = self.app.accounts.request_login_otp(phone="01755550001")
        with self.assertRaises(AccountError):
            self.app.accounts.verify_login_otp(sent["otp_id"], "000000")

    def test_otp_unknown_phone_no_leak(self):
        sent = self.app.accounts.request_login_otp(phone="01999999999")
        self.assertTrue(sent["sent"])
        self.assertIsNone(sent.get("otp_id"))


class TestParentLinks(unittest.TestCase):
    def setUp(self):
        self.app = create_app(llm=MockLLMProvider())
        self.summary = self.app.bootstrap_centre(create_sample_batches=True)
        self.actor = self.summary["roles"]["owner"]
        self.batch = self.summary["batch_ids"][0]
        self.sid, _ = self.app.admission.admit_student(
            name="Child One",
            batch_id=self.batch,
            student_phone="01766660001",
            actor_id=self.actor,
        )
        self.parent = self.app.accounts.create_account(
            role="parent", phone="01766660099", display_name="Parent"
        )

    def test_parent_link_and_view(self):
        link = self.app.accounts.link_parent_to_student(
            self.parent["id"], self.sid, actor_id=self.actor
        )
        self.assertTrue(link["id"])
        view = self.app.accounts.parent_view(self.parent["id"])
        self.assertEqual(len(view["children"]), 1)
        self.assertEqual(view["children"][0]["student"]["name"], "Child One")

    def test_non_parent_cannot_parent_view(self):
        student_acct = self.app.accounts.create_account(phone="01766660002")
        with self.assertRaises(AccessDeniedError):
            self.app.accounts.parent_view(student_acct["id"])


class TestThreadTakeoverAndPriority(unittest.TestCase):
    def setUp(self):
        self.app = create_app(llm=MockLLMProvider())
        self.summary = self.app.bootstrap_centre(create_sample_batches=True)
        self.actor = self.summary["roles"]["owner"]
        self.batch = self.summary["batch_ids"][0]
        self.sid, _ = self.app.admission.admit_student(
            name="Thread Student",
            batch_id=self.batch,
            student_phone="01777770001",
            actor_id=self.actor,
        )
        # ungrounded question → flagged
        self.app.solve.ask(
            student_id=self.sid,
            question="What is the capital of Atlantis lore mythology?",
            subject="history",
            topic="mythology",
        )

    def test_flagged_priority_queue(self):
        queue = self.app.accounts.flagged_thread_priority_queue()
        self.assertGreaterEqual(len(queue), 1)
        self.assertTrue(queue[0].get("flagged_for_teacher"))

    def test_teacher_reply(self):
        threads = self.app.solve.list_threads(self.sid)
        tid = threads[0]["id"]
        msg = self.app.accounts.teacher_reply_on_thread(
            thread_id=tid,
            teacher_id=self.actor,
            content="Come to class; we will cover this on the board.",
            student_id=self.sid,
        )
        self.assertEqual(msg["role"], "teacher")
        updated = self.app.data_layer.get("ai_threads", __import__("uuid").UUID(tid))
        self.assertFalse(updated.get("flagged_for_teacher"))


class TestAppHealth(unittest.TestCase):
    def test_accounts_in_health(self):
        h = create_app().health()
        self.assertTrue(h["services"]["accounts"])


if __name__ == "__main__":
    unittest.main()
