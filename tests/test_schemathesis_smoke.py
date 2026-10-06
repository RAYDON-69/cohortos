"""Health contract — always runs (no optional import)."""
from __future__ import annotations
import os, tempfile
from pathlib import Path
os.environ.setdefault("COHORTOS_JWT_SECRET", "fuzz-secret-not-for-prod-32chars")
os.environ.setdefault("COHORTOS_ENV", "test")
os.environ.setdefault("COHORTOS_SKIP_MODEL_DOWNLOAD", "1")
os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")

def test_schemathesis_health_no_500():
    from fastapi.testclient import TestClient
    from api.main import create_api_app
    td = Path(tempfile.mkdtemp())
    app = create_api_app(
        jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
        auth_db=str(td/"a.db"), cloud_db=str(td/"c.db"), founder_token="f",
    )
    assert TestClient(app).get("/health").status_code < 500
