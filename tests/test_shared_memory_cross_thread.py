"""P45: shared-memory URI and file DALs must share data across threads."""
from __future__ import annotations
import threading
import tempfile
import uuid
from pathlib import Path
from models.base import DataAccessLayer, TenantContext

def test_shared_memory_cross_thread_visibility():
    tenant = TenantContext(tenant_id=str(uuid.uuid4()), mode="offline-first")
    dal = DataAccessLayer(tenant, db_path=":memory:")
    dal.create("students", {"name": "main-thread", "phone": "01711111111"})
    key = dal._conn_key
    errors = []
    seen = []

    def worker():
        try:
            d2 = DataAccessLayer.__new__(DataAccessLayer)
            d2.tenant_context = tenant
            d2.db_path = dal.db_path
            d2._conn_key = key
            d2._is_shared_memory = True
            d2._closed = False
            d2.pending_operations = []
            d2.local_storage = {}
            d2._write_count = 0
            d2._backup_every = 999999
            rows = d2.get_all("students")
            seen.append(len(rows))
            if not any(r.get("name") == "main-thread" for r in rows):
                errors.append("row missing")
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)
    assert not errors, errors
    assert all(n >= 1 for n in seen), seen
    DataAccessLayer.close_all()

def test_file_db_cross_thread_visibility():
    td = tempfile.mkdtemp()
    path = str(Path(td) / "t.db")
    tenant = TenantContext(tenant_id=str(uuid.uuid4()), mode="offline-first")
    dal = DataAccessLayer(tenant, db_path=path)
    dal.create("students", {"name": "main-thread", "phone": "01711111111"})
    errors = []
    seen = []

    def worker():
        try:
            d2 = DataAccessLayer(tenant, db_path=path)
            rows = d2.get_all("students")
            seen.append(len(rows))
            if not any(r.get("name") == "main-thread" for r in rows):
                errors.append("row missing")
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)
    assert not errors, errors
    assert all(n >= 1 for n in seen), seen
    DataAccessLayer.close_all()
