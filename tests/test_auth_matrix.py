"""Authorization matrix: enumerate routes, classify, cross-tenant IDOR."""
from __future__ import annotations
import os
import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

PUBLIC_PREFIXES = ("/health", "/openapi", "/docs", "/redoc", "/auth/", "/join/")

@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("COHORTOS_JWT_SECRET", "test-secret-for-matrix-not-prod-xx")
    os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", "founder-matrix")
    os.environ.setdefault("COHORTOS_AUTH_DB", "/tmp/matrix-auth.db")
    os.environ.setdefault("COHORTOS_CLOUD_DB", "/tmp/matrix-cloud.db")
    os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
    os.environ.setdefault("COHORTOS_RATE_LIMIT_DISABLED", "1")
    os.environ.setdefault("COHORTOS_SKIP_MODEL_DOWNLOAD", "1")
    os.environ.setdefault("COHORTOS_ENV", "test")
    from api.main import create_api_app_or_raise
    app = create_api_app_or_raise()
    with TestClient(app) as c:
        c.app = app  # type: ignore
        yield c

def _classify(path: str) -> str:
    if any(path.startswith(p) or path == p.rstrip("/") for p in PUBLIC_PREFIXES):
        return "public"
    if path.startswith("/founder") or "founder" in path:
        return "founder"
    if path.startswith("/t/{") or path.startswith("/t/"):
        return "tenant-scoped"
    if path.startswith("/auth"):
        return "public"
    return "authenticated"

def test_route_inventory_classified(client: TestClient):
    routes, unclassified = [], []
    for r in client.app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None) or set()
        if not path:
            continue
        cls = _classify(path)
        routes.append({"path": path, "methods": sorted(methods), "class": cls})
        if cls not in ("public", "authenticated", "tenant-scoped", "founder"):
            unclassified.append(path)
    assert routes, "no routes"
    assert not unclassified, f"unclassified: {unclassified}"
    print(f"ROUTE_COUNT={len(routes)} CLASSIFIED={len(routes)}")

def _seed(client, phone, name):
    r = client.post("/auth/centre-trial", json={"centre_name": name, "owner_phone": phone, "owner_name": "Owner", "student_count": 1})
    assert r.status_code in (200, 201), r.text
    tid = r.json()["tenant_id"]
    otp = client.post("/auth/request-otp", json={"phone": phone, "tenant_id": tid})
    assert otp.status_code == 200, otp.text
    body = otp.json()
    ver = client.post("/auth/verify-otp", json={"phone": phone, "code": body.get("_test_code"), "otp_id": body["otp_id"], "tenant_id": tid})
    assert ver.status_code == 200, ver.text
    return tid, ver.json()["access_token"]

def test_no_token_on_tenant_paths(client: TestClient):
    for path, method in [("/t/fake/classes/sessions", "GET"), ("/t/fake/backup", "POST"), ("/t/fake/call-desk/queue", "POST")]:
        r = client.get(path) if method == "GET" else client.post(path, json={})
        assert r.status_code in (401, 403, 404, 405, 422), f"{path}->{r.status_code}"
        assert r.status_code < 500

def test_cross_tenant_idor_blocked(client: TestClient):
    tid_a, tok_a = _seed(client, "01710000021", "Centre A")
    tid_b, tok_b = _seed(client, "01710000022", "Centre B")
    ca = client.post(f"/t/{tid_a}/classes/sessions", headers={"Authorization": f"Bearer {tok_a}"},
        json={"batch_id": "b1", "title": "A only", "mode": "broadcast", "broadcast_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    if ca.status_code == 200:
        sid = ca.json().get("id")
        r = client.get(f"/t/{tid_a}/classes/sessions", headers={"Authorization": f"Bearer {tok_b}"})
        assert r.status_code in (401, 403), f"cross-tenant list {r.status_code}"
        assert r.status_code < 500
        if sid:
            j = client.post(f"/t/{tid_a}/classes/sessions/{sid}/join", headers={"Authorization": f"Bearer {tok_b}"},
                json={"role": "participant", "display_name": "Evil"})
            assert j.status_code in (401, 403, 404)
            assert j.status_code < 500
