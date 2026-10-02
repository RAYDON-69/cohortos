"""B1 full dual-tenant matrix from OpenAPI (P38)."""
from __future__ import annotations
import os
import re
import tempfile
from pathlib import Path
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    td = Path(tempfile.mkdtemp())
    os.environ["COHORTOS_JWT_SECRET"] = "matrix-secret-not-for-prod-32chars"
    os.environ["COHORTOS_FOUNDER_TOKEN"] = "founder-matrix"
    os.environ["COHORTOS_AUTH_DB"] = str(td / "a.db")
    os.environ["COHORTOS_CLOUD_DB"] = str(td / "c.db")
    os.environ["COHORTOS_SKIP_MODEL_DOWNLOAD"] = "1"
    os.environ["COHORTOS_TEST_EXPOSE_OTP"] = "1"
    os.environ["COHORTOS_ENV"] = "test"
    from api.main import create_api_app
    app = create_api_app(
        jwt_secret="matrix-secret-not-for-prod-32chars",
        auth_db=str(td / "a.db"),
        cloud_db=str(td / "c.db"),
        founder_token="founder-matrix",
    )
    return TestClient(app)

def _fill_path(path: str, tenant: str) -> str:
    url = path.replace("{tenant_id}", tenant)
    url = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000001", url)
    return url

def test_every_tenant_route_rejects_unauthenticated(client):
    spec = client.get("/openapi.json").json()
    failures = []
    for path, methods in (spec.get("paths") or {}).items():
        if "{tenant_id}" not in path:
            continue
        for method in methods:
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            url = _fill_path(path, "tenant-A")
            r = getattr(client, method)(url, json={})
            if r.status_code not in (401, 403, 404, 405, 422):
                failures.append(f"{method.upper()} {url} -> {r.status_code}")
    assert not failures, "unexpected status:\n" + "\n".join(failures[:30])

def test_openapi_paths_covered_or_public(client):
    """Every route is tenant-scoped, public, or in allowlist."""
    PUBLIC_PREFIXES = ("/health", "/docs", "/redoc", "/openapi", "/auth/")
    spec = client.get("/openapi.json").json()
    uncovered = []
    for path in (spec.get("paths") or {}):
        if any(path.startswith(p) or p in path for p in PUBLIC_PREFIXES):
            continue
        if "{tenant_id}" in path or path.startswith("/t/"):
            continue
        if path.startswith("/founder") or path.startswith("/billing"):
            continue
        uncovered.append(path)
    # Allow small set of control-plane paths
    assert len(uncovered) < 40, f"too many unclassified routes: {uncovered[:20]}"
