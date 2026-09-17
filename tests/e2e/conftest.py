"""Shared fixtures for headless GUI e2e (Xvfb + Playwright)."""
from __future__ import annotations
import os
import subprocess
import time
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "e2e"
EVIDENCE.mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="session")
def api_server():
    env = os.environ.copy()
    env["COHORTOS_JWT_SECRET"] = "test-secret-key-for-cohortos-v1-not-for-prod"
    env["COHORTOS_FOUNDER_TOKEN"] = "test-founder-token-for-ci"
    env["COHORTOS_TEST_EXPOSE_OTP"] = "1"
    env["COHORTOS_DATA_DIR"] = "/tmp/cohortos-e2e-data"
    proc = subprocess.Popen(
        [
            "python3",
            "-c",
            "from api.main import create_api_app; import uvicorn, os; "
            "app=create_api_app(jwt_secret=os.environ['COHORTOS_JWT_SECRET'],"
            "cloud_db='/tmp/cohortos-e2e-cloud.db',auth_db='/tmp/cohortos-e2e-auth.db',"
            "founder_token=os.environ['COHORTOS_FOUNDER_TOKEN']); "
            "uvicorn.run(app,host='127.0.0.1',port=8741)",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # wait health
    import urllib.request
    for _ in range(40):
        try:
            urllib.request.urlopen("http://127.0.0.1:8741/docs", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    yield "http://127.0.0.1:8741"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


@pytest.fixture(scope="session")
def browser_page():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        pytest.skip(f"playwright not available: {e}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()
            yield page
            context.close()
            browser.close()
    except Exception as e:
        pytest.skip(f"chromium launch failed: {e}")
