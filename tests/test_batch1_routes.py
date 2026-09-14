"""Batch 1 — wire missing exam / vault / staff-role routes (PRD gap matrix §27)."""
from __future__ import annotations

import os
import unittest
from datetime import date

os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")
os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")

from fastapi.testclient import TestClient
from api.main import create_api_app


def _auth_headers(client: TestClient, phone: str, centre_name: str) -> tuple[dict, str]:
    r = client.post(
        "/auth/centre-trial",
        json={
            "centre_name": centre_name,
            "owner_phone": phone,
            "owner_name": "Owner",
        },
    )
    assert r.status_code == 200, r.text
    tid = r.json()["tenant_id"]
    r = client.post("/auth/request-otp", json={"phone": phone})
    assert r.status_code == 200, r.text
    r2 = client.post(
        "/auth/verify-otp",
        json={
            "otp_id": r.json()["otp_id"],
            "code": r.json()["_test_code"],
            "tenant_id": r.json()["tenant_id"],
        },
    )
    assert r2.status_code == 200, r2.text
    return {"Authorization": f"Bearer {r2.json()['access_token']}"}, tid


class TestBatch1ExamRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_api_app(
            jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
            cloud_db=":memory:",
            auth_db=":memory:",
            founder_token=os.environ["COHORTOS_FOUNDER_TOKEN"],
        )
        cls.client = TestClient(cls.app)

    def test_create_enter_complete_and_analytics(self):
        h, tid = _auth_headers(self.client, "01711000001", "Exam Centre")
        # batch + student
        r = self.client.post(
            f"/t/{tid}/batches",
            json={"days": ["Sat", "Mon"], "hour": 10, "name": "Batch A"},
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        bid = r.json().get("batch_id") or (r.json().get("batch") or {}).get("id")
        r = self.client.post(
            f"/t/{tid}/students",
            json={"name": "S1", "batch_id": bid, "phone": "01721000001"},
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.json().get("student_id") or (r.json().get("student") or {}).get("id")

        today = date.today().isoformat()
        r = self.client.post(
            f"/t/{tid}/exams",
            json={
                "name": "Weekly 1",
                "exam_date": today,
                "batch_id": bid,
                "chapter_or_topic": "kinematics",
                "subject": "physics",
                "is_ad_hoc": True,
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        exam_id = r.json()["exam_id"]
        self.assertTrue(exam_id)

        r = self.client.post(
            f"/t/{tid}/exams/{exam_id}/results",
            json={
                "student_id": sid,
                "section_scores": [
                    {"key": "score", "marks_obtained": 70, "max_marks": 100}
                ],
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("result", r.json())

        r = self.client.get(f"/t/{tid}/exams/{exam_id}/results", headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(len(r.json().get("results") or []) >= 1)

        r = self.client.post(f"/t/{tid}/exams/{exam_id}/complete", headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get("completed"))

        r = self.client.get(f"/t/{tid}/analytics/heatmap?batch_id={bid}", headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("topics", r.json())

        r = self.client.get(
            f"/t/{tid}/analytics/struggle?batch_id={bid}", headers=h
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("students", r.json())

        r = self.client.get(f"/t/{tid}/students/{sid}/results", headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("results", r.json())


class TestBatch1VaultRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_api_app(
            jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
            cloud_db=":memory:",
            auth_db=":memory:",
            founder_token=os.environ["COHORTOS_FOUNDER_TOKEN"],
        )
        cls.client = TestClient(cls.app)

    def test_create_rules_relax_restore_access(self):
        h, tid = _auth_headers(self.client, "01711000002", "Vault Centre")
        r = self.client.post(
            f"/t/{tid}/vault",
            json={
                "title": "Lecture PDF",
                "resource_type": "pdf",
                "topic": "kinematics",
                "protection_level": "owner_only",
                "actor_role": "owner",
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["resource_id"]
        self.assertTrue(rid)

        r = self.client.put(
            f"/t/{tid}/vault/{rid}/access-rules",
            json={
                "operator": "AND",
                "rules": [{"kind": "always_allow", "value": None}],
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post(
            f"/t/{tid}/vault/{rid}/relax",
            json={"actor_role": "owner"},
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(
            (r.json().get("resource") or {}).get("protection_level"), "relaxed"
        )

        r = self.client.post(
            f"/t/{tid}/vault/{rid}/restore",
            json={"actor_role": "owner"},
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)

        # student for access eval
        r = self.client.post(
            f"/t/{tid}/batches",
            json={"days": ["Sat"], "hour": 9, "name": "B"},
            headers=h,
        )
        bid = r.json().get("batch_id") or (r.json().get("batch") or {}).get("id")
        r = self.client.post(
            f"/t/{tid}/students",
            json={"name": "S", "batch_id": bid, "phone": "01721000099"},
            headers=h,
        )
        sid = r.json().get("student_id") or (r.json().get("student") or {}).get("id")

        r = self.client.get(
            f"/t/{tid}/vault/{rid}/access?student_id={sid}", headers=h
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("allowed", r.json())


class TestBatch1StaffRoleRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_api_app(
            jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
            cloud_db=":memory:",
            auth_db=":memory:",
            founder_token=os.environ["COHORTOS_FOUNDER_TOKEN"],
        )
        cls.client = TestClient(cls.app)

    def test_assign_role(self):
        h, tid = _auth_headers(self.client, "01711000003", "Staff Centre")
        r = self.client.post(
            f"/t/{tid}/staff",
            json={"name": "Desk One", "role": "desk", "phone": "01731000001"},
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        uid = r.json().get("user_id") or (r.json().get("user") or {}).get("id")
        self.assertTrue(uid)

        r = self.client.post(
            f"/t/{tid}/staff/{uid}/role",
            json={"role_name": "teacher", "is_owner": False},
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("role_name"), "teacher")
        user = r.json().get("user") or {}
        self.assertIn(
            (user.get("role") or user.get("role_name") or "").lower(),
            ("teacher",),
        )


if __name__ == "__main__":
    unittest.main()
