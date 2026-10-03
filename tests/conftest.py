"""Per-xdist-worker isolation for temp DBs and storage."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path

def pytest_configure(config):
    worker = os.environ.get("PYTEST_XDIST_WORKER") or "gw0"
    root = Path(tempfile.gettempdir()) / f"cohortos-xdist-{worker}"
    root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("COHORTOS_STORAGE_ROOT", str(root / "storage"))
    os.environ.setdefault("COHORTOS_TENANT_DB_DIR", str(root / "tenants"))
    Path(os.environ["COHORTOS_STORAGE_ROOT"]).mkdir(parents=True, exist_ok=True)
    Path(os.environ["COHORTOS_TENANT_DB_DIR"]).mkdir(parents=True, exist_ok=True)
