"""Phase 7c: BYO key failures + cost guard; vault content safety."""
from __future__ import annotations
import base64
import itertools
import os
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")

from fastapi.testclient import TestClient
from api.main import create_api_app
from services.llm_provider import LLMError, OfflineError

_phone = itertools.count(1940001000)


class TestPhase7c(unittest.TestCase):
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
            json={"centre_name": f"P7c{phone}", "owner_phone": phone, "owner_name": "O"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        tid = r.json()["tenant_id"]
        otp = self.client.post("/auth/request-otp", json={"phone": phone}).json()
        tok = self.client.post(
            "/auth/verify-otp",
            json={"otp_id": otp["otp_id"], "code": otp["_test_code"], "tenant_id": tid},
        ).json()
        return tid, {"Authorization": f"Bearer {tok['access_token']}"}

    def test_invalid_provider_key_graceful_copilot(self):
        tid, h = self._login()
        # Save bogus OpenAI key
        r = self.client.put(
            f"/t/{tid}/settings/ai-keys",
            headers=h,
            json={"provider": "openai", "api_key": "sk-invalid-not-real-key-000"},
        )
        self.assertIn(r.status_code, (200, 204), r.text)
        with mock.patch(
            "services.llm_provider.OpenAIProvider.complete",
            side_effect=LLMError("OpenAI HTTP 401: invalid_api_key"),
        ):
            r = self.client.post(
                f"/t/{tid}/ai/query",
                headers=h,
                json={"question": "How many students?"},
            )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertFalse(body.get("used_external_llm"))
        self.assertTrue(body.get("answer"))  # local grounded still works
        self.assertTrue(body.get("llm_error") or any(
            (t.get("error") for t in (body.get("tools_used") or []) if isinstance(t, dict))
        ), body)

    def test_invalid_key_tutor_graceful(self):
        tid, h = self._login()
        self.client.put(
            f"/t/{tid}/settings/ai-keys",
            headers=h,
            json={"provider": "anthropic", "api_key": "bad-key"},
        )
        # empty vault path still 200
        with mock.patch(
            "services.llm_provider.AnthropicProvider.complete",
            side_effect=OfflineError("Anthropic network error"),
        ):
            r = self.client.post(
                f"/t/{tid}/tutor/query",
                headers=h,
                json={"question": "Explain chapter 1", "batch_id": "b1"},
            )
        self.assertEqual(r.status_code, 200, r.text)
        # no crash; grounded false without docs
        self.assertIn("answer", r.json())

    def test_ai_cost_guard_blocks_runaway(self):
        tid, h = self._login()
        self.client.put(
            f"/t/{tid}/settings/ai-keys",
            headers=h,
            json={"provider": "groq", "api_key": "gsk_test"},
        )
        # Force cost guard to 2 calls
        old = os.environ.get("COHORTOS_AI_MAX_CALLS_PER_WINDOW")
        os.environ["COHORTOS_AI_MAX_CALLS_PER_WINDOW"] = "2"
        try:
            class _Resp:
                text = "ok from mock"
                model = "mock"

            with mock.patch(
                "services.llm_provider.GroqProvider.complete",
                return_value=_Resp(),
            ):
                r1 = self.client.post(f"/t/{tid}/ai/query", headers=h, json={"question": "q1"})
                r2 = self.client.post(f"/t/{tid}/ai/query", headers=h, json={"question": "q2"})
                r3 = self.client.post(f"/t/{tid}/ai/query", headers=h, json={"question": "q3"})
            self.assertEqual(r1.status_code, 200, r1.text)
            self.assertEqual(r2.status_code, 200, r2.text)
            self.assertEqual(r3.status_code, 429, r3.text)
            self.assertIn("cost guard", r3.json().get("detail", "").lower())
        finally:
            if old is None:
                os.environ.pop("COHORTOS_AI_MAX_CALLS_PER_WINDOW", None)
            else:
                os.environ["COHORTOS_AI_MAX_CALLS_PER_WINDOW"] = old

    def test_upload_rejects_oversize(self):
        tid, h = self._login()
        # 25MB + 1 byte as base64 would be huge to allocate; send declared oversize by patching decode
        big = b"x" * (25 * 1024 * 1024 + 10)
        payload = base64.b64encode(big).decode()
        r = self.client.post(
            f"/t/{tid}/vault/upload",
            headers=h,
            json={
                "title": "huge",
                "filename": "huge.bin",
                "content_base64": payload,
                "content_type": "application/octet-stream",
            },
        )
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("25MB", r.json().get("detail", ""))

    def test_content_missing_and_corrupt_safe(self):
        tid, h = self._login()
        # missing resource
        r = self.client.get(f"/t/{tid}/vault/does-not-exist/content", headers=h)
        self.assertEqual(r.status_code, 404)
        # create resource without storage file
        cr = self.client.post(
            f"/t/{tid}/vault",
            headers=h,
            json={"title": "ghost", "resource_type": "pdf", "url": "", "topic": "t"},
        )
        self.assertEqual(cr.status_code, 200, cr.text)
        rid = cr.json()["resource_id"]
        r = self.client.get(f"/t/{tid}/vault/{rid}/content", headers=h)
        self.assertIn(r.status_code, (404, 422), r.text)

    def test_content_oversized_stored_rejected(self):
        tid, h = self._login()
        # Upload small then mock download returning oversized
        small = base64.b64encode(b"%PDF-1.1 tiny").decode()
        up = self.client.post(
            f"/t/{tid}/vault/upload",
            headers=h,
            json={
                "title": "p",
                "filename": "p.pdf",
                "content_base64": small,
                "content_type": "application/pdf",
            },
        )
        self.assertEqual(up.status_code, 200, up.text)
        rid = up.json()["resource_id"]

        class _BigStream:
            def read(self, n=-1):
                # return one byte over limit when asked max+1
                return b"z" * (25 * 1024 * 1024 + 1)

        class _Store:
            def is_configured(self):
                return True
            def exists(self, _id):
                return True
            def download(self, _id):
                return _BigStream()

        with mock.patch("services.storage_service.build_storage_provider", return_value=_Store()):
            r = self.client.get(f"/t/{tid}/vault/{rid}/content", headers=h)
        self.assertEqual(r.status_code, 413, r.text)
        self.assertIn("25MB", r.json().get("detail", ""))


if __name__ == "__main__":
    unittest.main()
