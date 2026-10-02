from __future__ import annotations
import io, zipfile
import pytest
from fastapi.testclient import TestClient

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COHORTOS_JWT_SECRET", "x"*32)
    monkeypatch.setenv("COHORTOS_FOUNDER_TOKEN", "founder-test")
    monkeypatch.setenv("COHORTOS_ENV", "test")
    monkeypatch.setenv("COHORTOS_AUTH_DB", str(tmp_path/"auth.db"))
    monkeypatch.setenv("COHORTOS_CLOUD_DB", str(tmp_path/"cloud.db"))
    monkeypatch.setenv("COHORTOS_SKIP_MODEL_DOWNLOAD", "1")
    from api.main import create_api_app
    app = create_api_app(jwt_secret="x"*32, auth_db=str(tmp_path/"auth.db"),
                         cloud_db=str(tmp_path/"cloud.db"), founder_token="founder-test")
    return TestClient(app)

def test_diagnostics_requires_auth(client):
    r = client.get("/t/tenant-a/diagnostics/export")
    assert r.status_code in (401, 403)

def test_diagnostics_bundle_redacts_phone():
    from services.diagnostics import build_diagnostics_bundle, redact
    assert "[REDACTED_PHONE]" in redact("call 01712345678")
    blob = build_diagnostics_bundle(log_lines=["user 01799998888 Bearer aaa.bbb.ccc"],
                                    versions={"api":"1.2.0"}, config={"jwt_secret":"x","env":"test"},
                                    extra_secrets=["x"])
    zf = zipfile.ZipFile(io.BytesIO(blob))
    assert "01799998888" not in zf.read("logs_tail.txt").decode()
    assert "jwt_secret" not in zf.read("config.json").decode()
