"""Regression: restore_backup validates ciphertext_b64 (400 not 500)."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
import pytest

os.environ.setdefault("COHORTOS_JWT_SECRET", "backup-reg-secret-not-for-prod-32")
os.environ.setdefault("COHORTOS_ENV", "test")
os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_RATE_LIMIT_DISABLED", "1")
os.environ.setdefault("COHORTOS_SKIP_MODEL_DOWNLOAD", "1")


def _client():
    from api.main import create_api_app
    from fastapi.testclient import TestClient
    td = Path(tempfile.mkdtemp())
    app = create_api_app(
        jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
        auth_db=str(td / "a.db"),
        cloud_db=str(td / "c.db"),
        founder_token="founder",
    )
    return TestClient(app, raise_server_exceptions=False)


def _auth(client):
    phone = "01715550001"
    r = client.post(
        "/auth/centre-trial",
        json={"centre_name": "B", "owner_phone": phone, "owner_name": "O", "student_count": 5},
    )
    assert r.status_code == 200, r.text
    r = client.post("/auth/request-otp", json={"phone": phone})
    body = r.json()
    r2 = client.post(
        "/auth/verify-otp",
        json={"otp_id": body["otp_id"], "code": body["_test_code"], "tenant_id": body["tenant_id"]},
    )
    tid = body["tenant_id"]
    return tid, {"Authorization": f"Bearer {r2.json()['access_token']}"}


def test_restore_missing_ciphertext_400():
    c = _client()
    tid, h = _auth(c)
    r = c.post(f"/t/{tid}/backup/restore", headers=h, json={})
    assert r.status_code == 400


def test_restore_bad_base64_400():
    c = _client()
    tid, h = _auth(c)
    r = c.post(f"/t/{tid}/backup/restore", headers=h, json={"ciphertext_b64": "!!!"})
    assert r.status_code == 400


def test_restore_wrong_type_400_or_422():
    c = _client()
    tid, h = _auth(c)
    r = c.post(f"/t/{tid}/backup/restore", headers=h, json={"ciphertext_b64": 1})
    assert r.status_code in (400, 422)
