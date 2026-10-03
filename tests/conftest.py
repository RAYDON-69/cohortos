"""Per-xdist-worker isolation for temp DBs and storage."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path

def pytest_configure(config):
    worker = os.environ.get("PYTEST_XDIST_WORKER") or "master"
    root = Path(tempfile.gettempdir()) / f"cohortos-xdist-{worker}-{os.getpid()}"
    root.mkdir(parents=True, exist_ok=True)
    os.environ["COHORTOS_STORAGE_ROOT"] = str(root / "storage")
    os.environ["COHORTOS_TENANT_DB_DIR"] = str(root / "tenants")
    os.environ["COHORTOS_AUTH_DB"] = str(root / "auth.db")
    os.environ["COHORTOS_CLOUD_DB"] = str(root / "cloud.db")
    Path(os.environ["COHORTOS_STORAGE_ROOT"]).mkdir(parents=True, exist_ok=True)
    Path(os.environ["COHORTOS_TENANT_DB_DIR"]).mkdir(parents=True, exist_ok=True)

def pytest_collection_modifyitems(config, items):
    # no-op marker for skip budget baseline
    pass


import pytest

@pytest.fixture(autouse=True)
def _isolate_dal():
    yield
    try:
        from models.base import DataAccessLayer
        DataAccessLayer.close_all()
    except Exception:
        pass
