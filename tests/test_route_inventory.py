"""OpenAPI route inventory: auth, tenant isolation, rate-limit allow-list."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("COHORTOS_JWT_SECRET", "route-inventory-secret-not-for-prod32")
os.environ.setdefault("COHORTOS_ENV", "test")
os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_SKIP_MODEL_DOWNLOAD", "1")
os.environ.setdefault("COHORTOS_RATE_LIMIT_DISABLED", "1")

PUBLIC_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/auth/centre-trial",
    "/auth/request-otp",
    "/auth/verify-otp",
    "/auth/refresh",
    "/auth/login",
)

# Exempt from "must be rate-limited" with justification
RATE_LIMIT_ALLOWLIST = {
    ("GET", "/health"): "liveness probe must not 429",
    ("GET", "/openapi.json"): "schema fetch for clients and CI",
    ("GET", "/docs"): "interactive docs in non-prod",
    ("GET", "/redoc"): "alternate docs UI",
}


def _app_client():
    from fastapi.testclient import TestClient

    from api.main import create_api_app

    td = Path(tempfile.mkdtemp())
    app = create_api_app(
        jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
        auth_db=str(td / "a.db"),
        cloud_db=str(td / "c.db"),
        founder_token="founder",
    )
    return app, TestClient(app)


def _is_public(path: str) -> bool:
    for p in PUBLIC_PREFIXES:
        if path == p or path.startswith(p + "/"):
            return True
    if path.startswith("/auth/"):
        return True
    return False


def test_route_inventory_auth_and_isolation():
    _app, client = _app_client()
    schema = client.get("/openapi.json").json()
    paths = schema.get("paths") or {}
    routes = []
    for path, methods in paths.items():
        for method in methods:
            if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"):
                routes.append((method.upper(), path))
    assert len(routes) >= 30, f"too few routes: {len(routes)}"

    unauth_fail = []
    for method, path in routes:
        if _is_public(path):
            continue
        url = path
        for seg in path.split("/"):
            if seg.startswith("{") and seg.endswith("}"):
                url = url.replace(seg, "x")
        r = client.request(method, url)
        if r.status_code not in (401, 403, 404, 405, 422):
            unauth_fail.append((method, path, r.status_code))
    assert not unauth_fail, f"unauthenticated access unexpected: {unauth_fail[:15]}"

    def trial(phone: str, name: str):
        r = client.post(
            "/auth/centre-trial",
            json={"centre_name": name, "owner_phone": phone, "owner_name": "O"},
        )
        assert r.status_code == 200, r.text
        tid = r.json()["tenant_id"]
        otp = client.post("/auth/request-otp", json={"phone": phone}).json()
        tok = client.post(
            "/auth/verify-otp",
            json={"otp_id": otp["otp_id"], "code": otp["_test_code"], "tenant_id": tid},
        ).json()
        return tid, tok["access_token"]

    _tid_a, tok_a = trial("01716660001", "CentreA")
    tid_b, _tok_b = trial("01716660002", "CentreB")
    ha = {"Authorization": f"Bearer {tok_a}"}
    r = client.get(f"/t/{tid_b}/students", headers=ha)
    assert r.status_code in (401, 403, 404), r.text
    print(f"route_inventory routes={len(routes)} unauth_ok isolation_ok")


def test_rate_limit_allowlist_documented():
    for (_m, _p), reason in RATE_LIMIT_ALLOWLIST.items():
        assert isinstance(reason, str) and len(reason) > 5
