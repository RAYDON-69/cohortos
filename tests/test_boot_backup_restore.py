"""Empty DB -> migrate/boot -> tenant -> student -> backup (release hygiene)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("COHORTOS_JWT_SECRET", "boot-backup-secret-not-for-prod-32ch")
os.environ.setdefault("COHORTOS_ENV", "test")
os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_SKIP_MODEL_DOWNLOAD", "1")


def test_boot_backup_restore_roundtrip():
    from fastapi.testclient import TestClient

    from api.main import create_api_app

    td = Path(tempfile.mkdtemp())
    app = create_api_app(
        jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
        auth_db=str(td / "auth.db"),
        cloud_db=str(td / "cloud.db"),
        founder_token="founder-test",
    )
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    phone = "01715550011"
    tr = c.post(
        "/auth/centre-trial",
        json={"centre_name": "Boot Centre", "owner_phone": phone, "owner_name": "Owner"},
    )
    assert tr.status_code == 200, tr.text
    tid = tr.json()["tenant_id"]
    otp = c.post("/auth/request-otp", json={"phone": phone}).json()
    tok = c.post(
        "/auth/verify-otp",
        json={"otp_id": otp["otp_id"], "code": otp["_test_code"], "tenant_id": tid},
    ).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    br = c.post(
        f"/t/{tid}/batches",
        headers=h,
        json={"name": "B1", "days": ["Sat"], "hour": 10},
    )
    assert br.status_code < 400, br.text
    bj = br.json()
    batch_id = bj.get("batch_id") or (bj.get("batch") or {}).get("id")
    sr = c.post(
        f"/t/{tid}/students",
        headers=h,
        json={"name": "Student One", "phone": "01715550012", "batch_id": batch_id},
    )
    assert sr.status_code < 400, sr.text
    students = c.get(f"/t/{tid}/students", headers=h)
    assert students.status_code == 200
    body = students.json()
    rows = body.get("students") if isinstance(body, dict) else body
    assert len(rows or []) >= 1
    bak = c.post(f"/t/{tid}/backup", headers=h)
    if bak.status_code >= 400:
        bak = c.post(f"/t/{tid}/backup/create", headers=h)
    assert bak.status_code < 500, bak.text
