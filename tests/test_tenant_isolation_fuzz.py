"""B1: tenant-scoped routes must not leak data cross-tenant."""
from __future__ import annotations
import os
import re
import tempfile
from pathlib import Path
import pytest

os.environ.setdefault("COHORTOS_JWT_SECRET", "tenant-fuzz-secret-not-for-prod-32")
os.environ.setdefault("COHORTOS_SKIP_MODEL_DOWNLOAD", "1")
os.environ.setdefault("COHORTOS_ENV", "test")
os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_RATE_LIMIT_DISABLED", "1")


def test_openapi_tenant_paths_are_scoped():
    from fastapi.testclient import TestClient
    from api.main import create_api_app

    td = Path(tempfile.mkdtemp())
    app = create_api_app(
        jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
        auth_db=str(td / "a.db"),
        cloud_db=str(td / "c.db"),
        founder_token="founder",
    )
    client = TestClient(app)
    spec = client.get("/openapi.json").json()
    paths = spec.get("paths") or {}
    tenant_paths = [p for p in paths if "{tenant_id}" in p or "/t/" in p]
    assert len(tenant_paths) > 10
    for p in list(tenant_paths)[:40]:
        url = p.replace("{tenant_id}", "tenant-A")
        while "{" in url:
            url = re.sub(r"\{[^}]+\}", "x", url)
        for method in paths[p].keys():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            r = (
                getattr(client, method)(url, json={})
                if method in ("post", "put", "patch")
                else getattr(client, method)(url)
            )
            assert r.status_code in (401, 403, 404, 405, 422), (
                f"unexpected {r.status_code} for unauth {method.upper()} {url}"
            )


def test_cross_tenant_student_list_isolated():
    from fastapi.testclient import TestClient
    from api.main import create_api_app

    td = Path(tempfile.mkdtemp())
    app = create_api_app(
        jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
        auth_db=str(td / "a.db"),
        cloud_db=str(td / "c.db"),
        founder_token="founder",
    )
    client = TestClient(app)

    def centre(phone, name):
        r = client.post(
            "/auth/centre-trial",
            json={
                "centre_name": name,
                "owner_phone": phone,
                "owner_name": "O",
                "student_count": 5,
            },
        )
        assert r.status_code == 200, r.text
        r = client.post("/auth/request-otp", json={"phone": phone})
        body = r.json()
        r2 = client.post(
            "/auth/verify-otp",
            json={
                "otp_id": body["otp_id"],
                "code": body["_test_code"],
                "tenant_id": body["tenant_id"],
            },
        )
        assert r2.status_code == 200, r2.text
        return body["tenant_id"], {
            "Authorization": f"Bearer {r2.json()['access_token']}"
        }

    tid_a, ha = centre("01716000001", "A")
    tid_b, hb = centre("01716000002", "B")
    client.post(
        f"/t/{tid_a}/students",
        headers=ha,
        json={"name": "SecretA", "phone": "01716000011"},
    )
    # B token must not list A's students
    r = client.get(f"/t/{tid_a}/students", headers=hb)
    assert r.status_code in (401, 403), r.text
    r2 = client.get(f"/t/{tid_b}/students", headers=hb)
    assert r2.status_code == 200, r2.text
    text = r2.text
    assert "SecretA" not in text
