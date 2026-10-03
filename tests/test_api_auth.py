"""
Backend v1 — Auth API + hardening (Parts A & B).
"""

from __future__ import annotations

import os
import uuid
import unittest

# Ensure JWT secret for all tests in this module
os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-key-for-cohortos-v1-not-for-prod")

from fastapi.testclient import TestClient

from api.main import create_api_app, create_api_app_or_raise
from api.auth import require_jwt_secret, require_auth_db, require_cloud_db, AuthConfigError, TokenService, TokenReuseError


class TestJWTSecretRequired(unittest.TestCase):
    def test_missing_secret_raises(self):
        old = os.environ.pop("COHORTOS_JWT_SECRET", None)
        old2 = os.environ.pop("JWT_SECRET", None)
        try:
            with self.assertRaises(AuthConfigError):
                require_jwt_secret()
        finally:
            if old is not None:
                os.environ["COHORTOS_JWT_SECRET"] = old
            else:
                os.environ["COHORTOS_JWT_SECRET"] = "test-secret-key-for-cohortos-v1-not-for-prod"
            if old2 is not None:
                os.environ["JWT_SECRET"] = old2

    def test_production_entry_requires_durable_dbs(self):
        """create_api_app_or_raise refuses missing / :memory: auth and cloud DB paths."""
        saved = {
            k: os.environ.pop(k, None)
            for k in (
                "COHORTOS_JWT_SECRET",
                "JWT_SECRET",
                "COHORTOS_AUTH_DB",
                "COHORTOS_CLOUD_DB",
            )
        }
        try:
            # No env at all
            with self.assertRaises(AuthConfigError):
                create_api_app_or_raise()
            # Secret only — still fails on auth db
            os.environ["COHORTOS_JWT_SECRET"] = "x" * 32
            with self.assertRaises(AuthConfigError):
                create_api_app_or_raise()
            # Auth set to memory — rejected
            os.environ["COHORTOS_AUTH_DB"] = ":memory:"
            os.environ["COHORTOS_CLOUD_DB"] = "/tmp/cloud.db"
            with self.assertRaises(AuthConfigError):
                require_auth_db()
            with self.assertRaises(AuthConfigError):
                create_api_app_or_raise()
            # Cloud missing
            os.environ["COHORTOS_AUTH_DB"] = "/tmp/auth.db"
            del os.environ["COHORTOS_CLOUD_DB"]
            with self.assertRaises(AuthConfigError):
                create_api_app_or_raise()
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            os.environ.setdefault(
                "COHORTOS_JWT_SECRET",
                "test-secret-key-for-cohortos-v1-not-for-prod",
            )


class TestAuthFlow(unittest.TestCase):
    def setUp(self):
        self.tenant_id = str(uuid.uuid4())
        self.app = create_api_app(jwt_secret=os.environ["COHORTOS_JWT_SECRET"])
        self.client = TestClient(self.app)
        self.registry = self.app.state.registry
        # Create account for OTP
        cm = self.registry.get_app(self.tenant_id)
        self.acct = cm.accounts.create_account(phone="01710000001", display_name="Auth User")

    def test_request_and_verify_otp(self):
        r = self.client.post(
            "/auth/request-otp",
            json={"phone": "01710000001", "tenant_id": self.tenant_id},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("otp_id"))
        code = body["_test_code"]

        r2 = self.client.post(
            "/auth/verify-otp",
            json={"otp_id": body["otp_id"], "code": code, "tenant_id": self.tenant_id},
        )
        self.assertEqual(r2.status_code, 200)
        tokens = r2.json()
        self.assertIn("access_token", tokens)
        # Refresh is httpOnly cookie (web) or body-compatible for clients that send it
        refresh = tokens.get("refresh_token") or r2.cookies.get("cohortos_refresh")
        self.assertTrue(refresh, "expected refresh token in body or cohortos_refresh cookie")

        me = self.client.get(
            "/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["account_id"], self.acct["id"])

    def test_protected_students_endpoint(self):
        r = self.client.post(
            "/auth/request-otp",
            json={"phone": "01710000001", "tenant_id": self.tenant_id},
        )
        code = r.json()["_test_code"]
        tokens = self.client.post(
            "/auth/verify-otp",
            json={"otp_id": r.json()["otp_id"], "code": code, "tenant_id": self.tenant_id},
        ).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        for path in ("students", "attendance", "payments"):
            resp = self.client.get(f"/t/{self.tenant_id}/{path}", headers=headers)
            self.assertEqual(resp.status_code, 200, msg=path)

    def test_refresh_rotation_and_reuse_revokes(self):
        r = self.client.post(
            "/auth/request-otp",
            json={"phone": "01710000001", "tenant_id": self.tenant_id},
        )
        code = r.json()["_test_code"]
        r2 = self.client.post(
            "/auth/verify-otp",
            json={"otp_id": r.json()["otp_id"], "code": code, "tenant_id": self.tenant_id},
        )
        self.assertEqual(r2.status_code, 200)
        old_refresh = r2.cookies.get("cohortos_refresh")
        self.assertTrue(old_refresh, "expected cohortos_refresh cookie after verify-otp")

        rotated = self.client.post("/auth/refresh", json={"refresh_token": old_refresh})
        self.assertEqual(rotated.status_code, 200)
        new_refresh = rotated.cookies.get("cohortos_refresh")
        self.assertTrue(new_refresh)
        self.assertNotEqual(old_refresh, new_refresh)

        # Reuse old refresh → family revoked
        reuse = self.client.post("/auth/refresh", json={"refresh_token": old_refresh})
        self.assertEqual(reuse.status_code, 401)

        # After reuse detection, family is dead — new_refresh should also fail
        again = self.client.post("/auth/refresh", json={"refresh_token": new_refresh})
        self.assertEqual(again.status_code, 401)

    def test_rate_limit_request_otp(self):
        old = os.environ.pop("COHORTOS_RATE_LIMIT_DISABLED", None)
        self.addCleanup(lambda: (os.environ.__setitem__("COHORTOS_RATE_LIMIT_DISABLED", old) if old is not None else os.environ.pop("COHORTOS_RATE_LIMIT_DISABLED", None)))

        for i in range(5):
            r = self.client.post(
                "/auth/request-otp",
                json={"phone": "01719999999", "tenant_id": self.tenant_id},
            )
            self.assertIn(r.status_code, (200, 429))
        r = self.client.post(
            "/auth/request-otp",
            json={"phone": "01719999999", "tenant_id": self.tenant_id},
        )
        self.assertEqual(r.status_code, 429)

    def test_cross_tenant_denied(self):
        tenant_b = str(uuid.uuid4())
        r = self.client.post(
            "/auth/request-otp",
            json={"phone": "01710000001", "tenant_id": self.tenant_id},
        )
        code = r.json()["_test_code"]
        tokens = self.client.post(
            "/auth/verify-otp",
            json={"otp_id": r.json()["otp_id"], "code": code, "tenant_id": self.tenant_id},
        ).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        for path in ("students", "attendance", "payments"):
            resp = self.client.get(f"/t/{tenant_b}/{path}", headers=headers)
            self.assertEqual(resp.status_code, 403, msg=path)
            self.assertIn("Cross-tenant", resp.json()["detail"])


if __name__ == "__main__":
    unittest.main()
