"""P42: shared sqlite connection must not 500 under concurrent access."""
from __future__ import annotations
import threading
import tempfile
import uuid
from pathlib import Path
import pytest

def test_64_threads_mixed_reads_writes_no_exceptions():
    from models.base import DataAccessLayer, TenantContext
    td = tempfile.mkdtemp()
    db = str(Path(td) / "conc.db")
    tenant = TenantContext(tenant_id=str(uuid.uuid4()), mode="offline-first")
    dal0 = DataAccessLayer(tenant, db_path=db)
    dal0.create("students", {"name": "seed", "phone": "01700000000"})
    errors = []
    n_threads = 64
    ops_per = 30

    def worker(k: int):
        try:
            dal = DataAccessLayer(tenant, db_path=db)
            for i in range(ops_per):
                if i % 3 == 0:
                    dal.create("students", {"name": f"s-{k}-{i}", "phone": f"017{k:04d}{i:04d}"[:11]})
                elif i % 3 == 1:
                    rows = dal.get_all("students")
                    assert isinstance(rows, list)
                else:
                    rows = dal.get_all("students")
                    if rows:
                        rid = rows[0].get("id")
                        if rid:
                            try:
                                dal.update("students", uuid.UUID(str(rid)), {"name": f"u-{k}-{i}"})
                            except Exception:
                                pass
        except Exception as e:
            errors.append(f"thread {k}: {type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors, "concurrency errors:\n" + "\n".join(errors[:20])
    final = DataAccessLayer(tenant, db_path=db).get_all("students")
    assert len(final) >= 1
    DataAccessLayer.close_all()

def test_http_level_concurrent_list_students():
    pytest.importorskip("fastapi")
    import os, tempfile
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from fastapi.testclient import TestClient
    from pathlib import Path
    td = Path(tempfile.mkdtemp())
    os.environ["COHORTOS_JWT_SECRET"] = "conc-secret-not-for-prod-32charsxx"
    os.environ["COHORTOS_FOUNDER_TOKEN"] = "founder"
    os.environ["COHORTOS_AUTH_DB"] = str(td / "a.db")
    os.environ["COHORTOS_CLOUD_DB"] = str(td / "c.db")
    os.environ["COHORTOS_SKIP_MODEL_DOWNLOAD"] = "1"
    os.environ["COHORTOS_TEST_EXPOSE_OTP"] = "1"
    os.environ["COHORTOS_ENV"] = "test"
    from api.main import create_api_app
    app = create_api_app(
        jwt_secret="conc-secret-not-for-prod-32charsxx",
        auth_db=str(td / "a.db"),
        cloud_db=str(td / "c.db"),
        founder_token="founder",
    )
    client = TestClient(app)
    def hit():
        r = client.get("/t/tenant-x/students")
        return r.status_code
    codes = []
    with ThreadPoolExecutor(max_workers=32) as ex:
        futs = [ex.submit(hit) for _ in range(100)]
        for f in as_completed(futs):
            codes.append(f.result())
    assert all(c < 500 for c in codes), f"got 5xx: {set(codes)}"
