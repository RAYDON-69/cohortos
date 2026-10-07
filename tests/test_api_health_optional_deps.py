"""Optional features must not block /health (P38)."""
from __future__ import annotations
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
import pytest
import tempfile

def test_health_with_minimal_env(tmp_path):
    """Spawn uvicorn with only required env; assert /health 200."""
    auth = tmp_path / "a.db"
    cloud = tmp_path / "c.db"
    env = os.environ.copy()
    env.update({
        "COHORTOS_JWT_SECRET": "health-test-secret-not-for-prod-xx",
        "COHORTOS_FOUNDER_TOKEN": "founder-health",
        "COHORTOS_AUTH_DB": str(auth),
        "COHORTOS_CLOUD_DB": str(cloud),
        "COHORTOS_SKIP_MODEL_DOWNLOAD": "1",
        "COHORTOS_TEST_EXPOSE_OTP": "1",
        "COHORTOS_ENV": "test",
        "COHORTOS_STORAGE_ROOT": str(tmp_path / "store"),
        "COHORTOS_RAG_DIR": str(tmp_path / "rag"),
        # Explicitly avoid chroma
        "COHORTOS_VECTOR_BACKEND": "sqlite-vec",
    })
    log = tmp_path / "api.log"
    port = "8765"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:create_api_app_or_raise", "--factory",
         "--host", "127.0.0.1", "--port", port],
        env=env, stdout=open(log, "w"), stderr=subprocess.STDOUT,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    try:
        ok = False
        for _ in range(40):
            if proc.poll() is not None:
                pytest.fail(f"API exited early: {log.read_text()[-2000:]}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                    if r.status == 200:
                        ok = True
                        break
            except Exception:
                time.sleep(0.5)
        assert ok, f"health never 200: {log.read_text()[-2000:]}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

def test_missing_auth_db_fails_loudly():
    """Without AUTH_DB, factory must raise (documents the CI root cause)."""
    from api.auth import require_auth_db, AuthConfigError
    import os
    os.environ.pop("COHORTOS_AUTH_DB", None)
    with pytest.raises(AuthConfigError):
        require_auth_db()
