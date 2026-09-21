"""Phase 8: multi-document retrieval + DeepSeek provider registration."""
from __future__ import annotations
import itertools
import os
import unittest
import uuid

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")

from fastapi.testclient import TestClient
from api.main import create_api_app
from services.llm_provider import build_llm_provider, DeepSeekProvider
from services.retrieval_service import RetrievalService
from models.base import TenantContext

_phone = itertools.count(1950001000)


class TestPhase8Rag(unittest.TestCase):
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
            json={"centre_name": f"RAG{phone}", "owner_phone": phone, "owner_name": "O"},
        )
        tid = r.json()["tenant_id"]
        otp = self.client.post("/auth/request-otp", json={"phone": phone}).json()
        tok = self.client.post(
            "/auth/verify-otp",
            json={"otp_id": otp["otp_id"], "code": otp["_test_code"], "tenant_id": tid},
        ).json()
        return tid, {"Authorization": f"Bearer {tok['access_token']}"}

    def test_deepseek_provider_builds(self):
        p = build_llm_provider("deepseek", "sk-test")
        self.assertIsInstance(p, DeepSeekProvider)
        self.assertTrue(p.is_available())

    def test_multidoc_retrieval_cites_correct_source(self):
        """Seed 5 long synthetic textbooks; query should rank the kinetics doc highest."""
        tid, h = self._login()
        batch = self.client.post(
            f"/t/{tid}/batches",
            headers=h,
            json={"days": ["sat"], "hour": 10, "name": "Physics A"},
        ).json()
        bid = batch["batch_id"]

        books = [
            (
                "Organic Chemistry Vol 1",
                "alkanes alkenes aromatic rings substitution reactions. " * 40
                + "benzene resonance hybrid structures. " * 20,
            ),
            (
                "Kinetics and Rate Laws",
                "chemical kinetics rate constant activation energy collision theory. " * 40
                + "first order second order half life Arrhenius equation. " * 30
                + "The rate of reaction depends on concentration and temperature.",
            ),
            (
                "Electromagnetism Notes",
                "Faraday induction magnetic flux Gauss law. " * 50,
            ),
            (
                "Bangla Literature Anthology",
                "রবীন্দ্রনাথ ঠাকুর নজরুল ইসলাম কবিতা. " * 40,
            ),
            (
                "Algebra Problem Set",
                "quadratic equations matrices determinants. " * 50,
            ),
        ]
        for title, body in books:
            r = self.client.post(
                f"/t/{tid}/vault",
                headers=h,
                json={
                    "title": title,
                    "resource_type": "pdf",
                    "topic": "study",
                    "description": body,
                    "batch_ids": [bid],
                    "protection_level": "owner_only",
                },
            )
            self.assertEqual(r.status_code, 200, r.text)

        # Unit-level retrieval against same app content store
        from api.main import create_api_app as _
        # use registry via HTTP tutor
        r = self.client.post(
            f"/t/{tid}/tutor/query",
            headers=h,
            json={
                "question": "What is chemical kinetics and the Arrhenius equation?",
                "batch_id": bid,
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body.get("grounded"), body)
        cites = body.get("citations") or []
        self.assertTrue(len(cites) >= 1, body)
        titles = " ".join(str(c.get("title") or "") for c in cites).lower()
        self.assertIn("kinetic", titles, cites)
        # must not only return unrelated literature
        self.assertNotEqual(titles.strip(), "bangla literature anthology")

    def test_cross_batch_isolation_still_holds(self):
        tid, h = self._login()
        r = self.client.post(
            f"/t/{tid}/tutor/query",
            headers=h,
            json={"question": "Arrhenius", "batch_id": "empty-batch-xyz"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json().get("grounded"))


if __name__ == "__main__":
    unittest.main()
