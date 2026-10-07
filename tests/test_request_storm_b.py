"""Request storm: concurrent reads across tenants must not 5xx."""
from __future__ import annotations
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pytest

def test_request_storm_no_5xx_unauth():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from api.main import create_api_app
    td = Path(tempfile.mkdtemp())
    os.environ.setdefault("COHORTOS_JWT_SECRET", "storm-secret-not-for-prod-32charsx")
    os.environ.setdefault("COHORTOS_SKIP_MODEL_DOWNLOAD", "1")
    os.environ.setdefault("COHORTOS_ENV", "test")
    os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
    os.environ.setdefault("COHORTOS_RATE_LIMIT_DISABLED", "1")
    app = create_api_app(
        jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
        auth_db=str(td / "a.db"),
        cloud_db=str(td / "c.db"),
        founder_token="founder",
    )
    client = TestClient(app)
    paths = [f"/t/tenant-{i % 3}/students" for i in range(50)]

    def hit(p):
        return client.get(p).status_code

    codes = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        for c in as_completed([ex.submit(hit, p) for p in paths]):
            codes.append(c.result())
    assert all(c < 500 for c in codes), f"5xx present: {set(codes)}"
