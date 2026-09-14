"""Bulk biometric device_user_id linking — malformed rows, duplicates, student-not-found."""
from __future__ import annotations

import itertools
import os
import unittest

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")

from fastapi.testclient import TestClient
from api.main import create_api_app

_phone = itertools.count(1719999200)


class TestBiometricLinkBulk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_api_app(
            jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
            cloud_db=":memory:",
            auth_db=":memory:",
            founder_token=os.environ["COHORTOS_FOUNDER_TOKEN"],
        )
        cls.client = TestClient(cls.app)

    def _fresh_tenant_with_student(self):
        n = next(_phone)
        phone = f"01{n:09d}"[-11:]
        r = self.client.post(
            "/auth/centre-trial",
            json={"centre_name": f"Bulk {phone}", "owner_phone": phone, "owner_name": "Owner"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        tenant_id = r.json()["tenant_id"]
        otp = self.client.post("/auth/request-otp", json={"phone": phone})
        body = otp.json()
        r2 = self.client.post(
            "/auth/verify-otp",
            json={
                "otp_id": body["otp_id"],
                "code": body["_test_code"],
                "tenant_id": body.get("tenant_id") or tenant_id,
            },
        )
        self.assertEqual(r2.status_code, 200, r2.text)
        headers = {"Authorization": f"Bearer {r2.json()['access_token']}"}

        br = self.client.post(
            f"/t/{tenant_id}/batches",
            headers=headers,
            json={"days": ["Sat"], "hour": 10, "name": "B"},
        )
        self.assertEqual(br.status_code, 200, br.text)
        batch_id = br.json().get("batch_id") or (br.json().get("batch") or {}).get("id")

        sr = self.client.post(
            f"/t/{tenant_id}/students",
            headers=headers,
            json={"name": "Student One", "batch_id": batch_id, "phone": phone},
        )
        self.assertIn(sr.status_code, (200, 201), sr.text)
        sj = sr.json()
        student_id = sj.get("student_id") or sj.get("id") or (sj.get("student") or {}).get("id")
        # fetch roll if present
        st_list = self.client.get(f"/t/{tenant_id}/students", headers=headers)
        students = st_list.json().get("students") or []
        roll = None
        for s in students:
            if str(s.get("id")) == str(student_id):
                roll = s.get("roll")
                break
        return tenant_id, headers, student_id, roll

    def test_bulk_happy_path_by_student_id(self):
        tenant_id, headers, student_id, _roll = self._fresh_tenant_with_student()
        r = self.client.post(
            f"/t/{tenant_id}/attendance/biometric/link-bulk",
            headers=headers,
            json={"rows": [{"student_id": student_id, "device_user_id": "101"}]},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["linked"], 1)
        self.assertEqual(r.json()["errors"], [])

    def test_bulk_happy_path_by_roll(self):
        tenant_id, headers, _sid, roll = self._fresh_tenant_with_student()
        if not roll:
            self.skipTest("no roll on student")
        r = self.client.post(
            f"/t/{tenant_id}/attendance/biometric/link-bulk",
            headers=headers,
            json={"rows": [{"roll": roll, "device_user_id": "202"}]},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["linked"], 1)
        self.assertEqual(r.json().get("errors") or [], [])

    def test_bulk_malformed_missing_device_user_id(self):
        tenant_id, headers, student_id, _roll = self._fresh_tenant_with_student()
        r = self.client.post(
            f"/t/{tenant_id}/attendance/biometric/link-bulk",
            headers=headers,
            json={
                "rows": [
                    {"student_id": student_id},  # missing device_user_id
                    {"student_id": student_id, "device_user_id": "   "},  # blank
                ]
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["linked"], 0)
        self.assertGreaterEqual(len(body["errors"]), 2)
        for err in body["errors"]:
            self.assertIn("device_user_id", err.get("error", "").lower())

    def test_bulk_student_not_found(self):
        tenant_id, headers, _sid, _roll = self._fresh_tenant_with_student()
        r = self.client.post(
            f"/t/{tenant_id}/attendance/biometric/link-bulk",
            headers=headers,
            json={
                "rows": [
                    {"student_id": "00000000-0000-0000-0000-000000000099", "device_user_id": "303"},
                    {"roll": "NO-SUCH-ROLL", "device_user_id": "304"},
                ]
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["linked"], 0)
        self.assertEqual(len(body["errors"]), 2)
        for err in body["errors"]:
            self.assertIn("student not found", err.get("error", "").lower())

    def test_bulk_duplicate_device_user_id_two_students(self):
        """Same device_user_id mapped to two students — both links succeed at API layer;
        last write wins on lookup; both reported linked (no silent drop)."""
        tenant_id, headers, student_id, _roll = self._fresh_tenant_with_student()
        # second student
        batches = self.client.get(f"/t/{tenant_id}/batches", headers=headers).json().get("batches") or []
        batch_id = batches[0]["id"] if batches else None
        sr2 = self.client.post(
            f"/t/{tenant_id}/students",
            headers=headers,
            json={"name": "Student Two", "batch_id": batch_id, "phone": "01710000099"},
        )
        self.assertIn(sr2.status_code, (200, 201), sr2.text)
        s2 = sr2.json()
        student_id_2 = s2.get("student_id") or s2.get("id") or (s2.get("student") or {}).get("id")
        self.assertTrue(student_id_2)

        r = self.client.post(
            f"/t/{tenant_id}/attendance/biometric/link-bulk",
            headers=headers,
            json={
                "rows": [
                    {"student_id": student_id, "device_user_id": "DUP-1"},
                    {"student_id": student_id_2, "device_user_id": "DUP-1"},
                ]
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        # Both rows process; API does not reject duplicate device_user_id at bulk layer
        self.assertEqual(body["linked"], 2, body)
        self.assertEqual(body.get("errors") or [], [])

    def test_bulk_mixed_valid_and_invalid(self):
        tenant_id, headers, student_id, _roll = self._fresh_tenant_with_student()
        r = self.client.post(
            f"/t/{tenant_id}/attendance/biometric/link-bulk",
            headers=headers,
            json={
                "rows": [
                    {"student_id": student_id, "device_user_id": "OK-1"},
                    {"device_user_id": "NO-STUDENT"},
                    {"student_id": student_id, "device_user_id": ""},
                ]
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["linked"], 1)
        self.assertEqual(len(body["errors"]), 2)

    def test_bulk_empty_rows(self):
        tenant_id, headers, _sid, _roll = self._fresh_tenant_with_student()
        r = self.client.post(
            f"/t/{tenant_id}/attendance/biometric/link-bulk",
            headers=headers,
            json={"rows": []},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["linked"], 0)
        self.assertEqual(r.json()["errors"], [])


if __name__ == "__main__":
    unittest.main()
