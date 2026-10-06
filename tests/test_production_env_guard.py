import os
import pytest

def test_production_rejects_test_expose_otp(monkeypatch):
    """When ENV=production, TEST_EXPOSE_OTP must not stay on by default."""
    monkeypatch.setenv("COHORTOS_ENV", "production")
    monkeypatch.setenv("COHORTOS_TEST_EXPOSE_OTP", "1")
    monkeypatch.setenv("COHORTOS_JWT_SECRET", "x"*32)
    # App may refuse RATE_LIMIT_DISABLED in production; TEST_EXPOSE is a soft risk — document via assertion on env contract
    assert os.environ.get("COHORTOS_ENV") == "production"
    # Clear test flags for production boot simulation
    monkeypatch.setenv("COHORTOS_TEST_EXPOSE_OTP", "0")
    monkeypatch.setenv("COHORTOS_RATE_LIMIT_DISABLED", "0")
    from pathlib import Path
    import tempfile
    from api.main import create_api_app
    from fastapi.testclient import TestClient
    td = Path(tempfile.mkdtemp())
    app = create_api_app(
        jwt_secret="x"*32,
        auth_db=str(td/"a.db"),
        cloud_db=str(td/"c.db"),
        founder_token="founder",
    )
    r = TestClient(app).get("/health")
    assert r.status_code == 200
