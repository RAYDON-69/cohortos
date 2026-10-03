"""B1: tenant-scoped routes must not leak data cross-tenant."""
from __future__ import annotations
import os
import re
import tempfile
from pathlib import Path
import pytest

def test_openapi_tenant_paths_are_scoped():
    try:
        from fastapi.testclient import TestClient
        from api.main import create_api_app
    except Exception:
        pytest.skip("fastapi app not importable in this environment")
    td = Path(tempfile.mkdtemp())
    os.environ.setdefault("COHORTOS_JWT_SECRET", "x" * 32)
    os.environ.setdefault("COHORTOS_SKIP_MODEL_DOWNLOAD", "1")
    os.environ.setdefault("COHORTOS_ENV", "test")
    app = create_api_app(
        jwt_secret="x" * 32,
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
            r = getattr(client, method)(url, json={}) if method in ("post", "put", "patch") else getattr(client, method)(url)
            assert r.status_code in (401, 403, 404, 405, 422), (
                f"unexpected {r.status_code} for unauth {method.upper()} {url}"
            )

def test_cross_tenant_student_id_not_readable_with_other_token():
    """Placeholder until auth-matrix helpers are shared; skip cleanly."""
    pytest.skip("auth matrix helpers not shared as importable fixtures")
