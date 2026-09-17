"""Live Groq + NIM provider calls — requires env keys; skips if missing."""
from __future__ import annotations
import itertools
import os
import unittest

os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")
os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "test-founder-token-for-ci")

from fastapi.testclient import TestClient
from api.main import create_api_app

_phone = itertools.count(1918888000)


def _login(client):
    n = next(_phone)
    phone = f"01{n:09d}"[-11:]
    r = client.post("/auth/centre-trial", json={"centre_name": f"L{phone}", "owner_phone": phone, "owner_name": "O"})
    assert r.status_code == 200, r.text
    tid = r.json()["tenant_id"]
    otp = client.post("/auth/request-otp", json={"phone": phone}).json()
    tok = client.post(
        "/auth/verify-otp",
        json={"otp_id": otp["otp_id"], "code": otp["_test_code"], "tenant_id": tid},
    ).json()
    return tid, {"Authorization": f"Bearer {tok['access_token']}"}


class TestLiveLLM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Fresh limiter per class
        cls.app = create_api_app(
            jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
            cloud_db=":memory:",
            auth_db=":memory:",
            founder_token=os.environ["COHORTOS_FOUNDER_TOKEN"],
        )
        cls.client = TestClient(cls.app)

    def test_groq_live_grounded(self):
        key = os.environ.get("COHORTOS_GROQ_API_KEY") or os.environ.get("GROQ_API_KEY")
        if not key:
            self.skipTest("COHORTOS_GROQ_API_KEY not set")
        tid, h = _login(self.client)
        r = self.client.put(
            f"/t/{tid}/settings/ai-keys",
            headers=h,
            json={"provider": "groq", "api_key": key},
        )
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post(
            f"/t/{tid}/ai/query",
            headers=h,
            json={"question": "How many students are enrolled? Answer with the number from grounded data."},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body.get("provider_configured"), body)
        self.assertEqual((body.get("provider") or "").lower(), "groq")
        self.assertIn("grounded", body)
        self.assertEqual(body["grounded"]["student_count"], 0)
        # Real network path: either external answer OR provider HTTP error in tools_used
        external = body.get("used_external_llm")
        errs = [x for x in (body.get("tools_used") or []) if x.get("tool") == "external_llm"]
        self.assertTrue(
            external or errs,
            f"expected live Groq path, got {body}",
        )
        if external:
            self.assertTrue(body.get("answer"))
        else:
            # Document real upstream failure (e.g. Cloudflare 1010 from CI IP)
            self.assertTrue(errs[0].get("error"), errs)

    def test_nim_live_grounded(self):
        key = os.environ.get("COHORTOS_NIM_API_KEY") or os.environ.get("NIM_API_KEY") or os.environ.get("NVIDIA_API_KEY")
        if not key:
            self.skipTest("COHORTOS_NIM_API_KEY not set")
        tid, h = _login(self.client)
        r = self.client.put(
            f"/t/{tid}/settings/ai-keys",
            headers=h,
            json={"provider": "nim", "api_key": key},
        )
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post(
            f"/t/{tid}/ai/query",
            headers=h,
            json={"question": "How many batches exist? Use only grounded data."},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body.get("provider_configured"), body)
        self.assertIn((body.get("provider") or "").lower(), ("nim", "nvidia", "nvidia_nim", "nvidia-nim"))
        self.assertEqual(body["grounded"]["batch_count"], 0)
        external = body.get("used_external_llm")
        errs = [x for x in (body.get("tools_used") or []) if x.get("tool") == "external_llm"]
        self.assertTrue(external or errs, f"expected live NIM path, got {body}")
        if external:
            self.assertTrue(body.get("answer"))


if __name__ == "__main__":
    unittest.main()
