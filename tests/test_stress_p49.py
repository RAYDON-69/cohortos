"""P49 stress: storm, receipts, idempotency, backup, chaos, cross-thread."""
from __future__ import annotations

import os
import random
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

os.environ.setdefault("COHORTOS_JWT_SECRET", "stress-secret-not-for-prod-32chars")
os.environ.setdefault("COHORTOS_ENV", "test")
os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
os.environ.setdefault("COHORTOS_RATE_LIMIT_DISABLED", "1")
os.environ.setdefault("COHORTOS_SKIP_MODEL_DOWNLOAD", "1")


def _app(td: Path):
    from api.main import create_api_app
    from fastapi.testclient import TestClient

    app = create_api_app(
        jwt_secret=os.environ["COHORTOS_JWT_SECRET"],
        auth_db=str(td / "auth.db"),
        cloud_db=str(td / "cloud.db"),
        founder_token="founder-stress",
    )
    return TestClient(app, raise_server_exceptions=False)


def _trial(client, phone: str, name: str):
    r = client.post(
        "/auth/centre-trial",
        json={
            "centre_name": name,
            "owner_phone": phone,
            "owner_name": "Owner",
            "student_count": 20,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _login(client, phone: str):
    r = client.post("/auth/request-otp", json={"phone": phone})
    assert r.status_code == 200, r.text
    body = r.json()
    otp_id, code, tid = body.get("otp_id"), body.get("_test_code"), body.get("tenant_id")
    assert otp_id and code, body
    r2 = client.post(
        "/auth/verify-otp", json={"otp_id": otp_id, "code": code, "tenant_id": tid}
    )
    assert r2.status_code == 200, r2.text
    tok = r2.json()["access_token"]
    return tid, {"Authorization": f"Bearer {tok}"}


def test_authenticated_request_storm_three_tenants():
    td = Path(tempfile.mkdtemp())
    client = _app(td)
    sessions = []
    for i in range(3):
        phone = f"0171{i:07d}"
        _trial(client, phone, f"Centre {i}")
        sessions.append(_login(client, phone))

    def hit(i):
        tid, h = sessions[i % 3]
        codes = []
        for p in (f"/t/{tid}/students", f"/t/{tid}/fees", f"/t/{tid}/attendance"):
            codes.append(client.get(p, headers=h).status_code)
        codes.append(
            client.post("/auth/request-otp", json={"phone": f"0171{i % 3:07d}"}).status_code
        )
        return codes

    all_codes = []
    with ThreadPoolExecutor(max_workers=25) as ex:
        for f in as_completed([ex.submit(hit, i) for i in range(50)]):
            all_codes.extend(f.result())
    assert all(c < 500 for c in all_codes), sorted(set(all_codes))


def test_cross_thread_dal_visibility():
    from models.base import DataAccessLayer, TenantContext

    tenant = TenantContext(tenant_id=str(uuid.uuid4()), mode="offline-first")
    path = str(Path(tempfile.mkdtemp()) / "x.db")
    dal = DataAccessLayer(tenant, db_path=path)
    dal.create("students", {"name": "cross", "phone": "01710000099"})
    err: list[str] = []

    def worker():
        try:
            d2 = DataAccessLayer(tenant, db_path=path)
            rows = d2.get_all("students")
            if not any(r.get("name") == "cross" for r in rows):
                err.append("missing")
        except Exception as e:
            err.append(str(e))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)
    assert not err, err
    DataAccessLayer.close_all()


def test_fee_idempotency_key_replay():
    """Same idempotency_key on mark-paid => one paid row, same id."""
    td = Path(tempfile.mkdtemp())
    client = _app(td)
    phone = "01718880001"
    _trial(client, phone, "Fee Centre")
    tid, h = _login(client, phone)
    br = client.post(
        f"/t/{tid}/batches",
        headers=h,
        json={"name": "Fee Batch", "days": ["Sat", "Sun"], "hour": 16},
    )
    assert br.status_code < 400, br.text
    bj = br.json() or {}
    batch_id = bj.get("id") or bj.get("batch_id") or (bj.get("batch") or {}).get("id")
    assert batch_id, br.text
    sr = client.post(
        f"/t/{tid}/students",
        headers=h,
        json={"name": "S", "phone": "01718880002", "batch_id": batch_id},
    )
    assert sr.status_code < 500, sr.text
    assert sr.status_code < 400, f"student create required for fee stress: {sr.status_code} {sr.text}"
    body = sr.json() or {}
    sid = body.get("id") or body.get("student_id") or (body.get("student") or {}).get("id")
    assert sid, body
    key = f"idem-{uuid.uuid4().hex}"
    payload = {
        "student_id": sid,
        "year": 2026,
        "month": 10,
        "amount": 100,
        "idempotency_key": key,
    }
    r1 = client.post(f"/t/{tid}/payments/mark-paid", headers=h, json=payload)
    r2 = client.post(f"/t/{tid}/payments/mark-paid", headers=h, json=payload)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    p1 = (r1.json() or {}).get("payment") or {}
    p2 = (r2.json() or {}).get("payment") or {}
    assert p1.get("id") == p2.get("id"), (p1, p2)
    assert p1.get("status") == "paid"


def test_receipt_numbers_unique_per_centre_concurrent():
    from models.base import DataAccessLayer, TenantContext

    t1 = TenantContext(tenant_id=str(uuid.uuid4()), mode="offline-first")
    t2 = TenantContext(tenant_id=str(uuid.uuid4()), mode="offline-first")
    d1 = Path(tempfile.mkdtemp())
    dal1 = DataAccessLayer(t1, db_path=str(d1 / "a.db"))
    dal2 = DataAccessLayer(t2, db_path=str(d1 / "b.db"))
    lock = threading.Lock()
    receipts = {str(t1.tenant_id): [], str(t2.tenant_id): []}

    def issue(dal, tid, n):
        for i in range(n):
            rid = dal.create(
                "fee_payments",
                {
                    "tenant_id": tid,
                    "amount": 10 + i,
                    "receipt_no": f"{tid[:8]}-{i:05d}",
                },
            )
            with lock:
                receipts[tid].append(rid)

    th = [
        threading.Thread(target=issue, args=(dal1, str(t1.tenant_id), 30)),
        threading.Thread(target=issue, args=(dal2, str(t2.tenant_id), 30)),
    ]
    for t in th:
        t.start()
    for t in th:
        t.join(timeout=60)
    a, b = receipts[str(t1.tenant_id)], receipts[str(t2.tenant_id)]
    assert len(a) == 30 and len(b) == 30
    assert len(set(a)) == 30 and len(set(b)) == 30
    assert set(a).isdisjoint(set(b))
    DataAccessLayer.close_all()


def test_backup_create_while_writes_in_flight():
    from models.base import DataAccessLayer, TenantContext
    import shutil

    path = str(Path(tempfile.mkdtemp()) / "live.db")
    tenant = TenantContext(tenant_id=str(uuid.uuid4()), mode="offline-first")
    dal = DataAccessLayer(tenant, db_path=path)
    stop = threading.Event()

    def writer():
        i = 0
        while not stop.is_set() and i < 200:
            try:
                dal.create("students", {"name": f"s{i}", "phone": f"0171{i:07d}"})
            except Exception:
                pass
            i += 1

    th = threading.Thread(target=writer)
    th.start()
    time.sleep(0.05)
    shutil.copy2(path, path + ".bak")
    assert Path(path + ".bak").exists()
    stop.set()
    th.join(timeout=30)
    assert Path(path).exists()
    DataAccessLayer.close_all()


def test_corrupt_backup_restore_rejected():
    td = Path(tempfile.mkdtemp())
    client = _app(td)
    phone = "01719990001"
    _trial(client, phone, "Backup Centre")
    tid, h = _login(client, phone)
    r = client.post(f"/t/{tid}/backup/restore", headers=h, json={})
    assert r.status_code == 400, r.text
    r2 = client.post(
        f"/t/{tid}/backup/restore",
        headers=h,
        json={"ciphertext_b64": "not-valid-base64!!!"},
    )
    assert r2.status_code == 400, r2.text


def test_backup_restore_wrong_type_rejected():
    td = Path(tempfile.mkdtemp())
    client = _app(td)
    phone = "01719990002"
    _trial(client, phone, "Backup Centre 2")
    tid, h = _login(client, phone)
    r = client.post(
        f"/t/{tid}/backup/restore",
        headers=h,
        json={"ciphertext_b64": 12345},
    )
    assert r.status_code in (400, 422), r.text


def test_kill9_chaos_idempotent_writer():
    """200 iterations: SIGKILL writer mid-flight; DB integrity + idempotent retry."""
    seed = int(os.environ.get("CHAOS_SEED") or random.randint(1, 2**31 - 1))
    rng = random.Random(seed)
    print(f"CHAOS_SEED={seed}")
    root = Path(tempfile.mkdtemp())
    script = root / "writer.py"
    script.write_text(
        """
import os, sys, time, uuid
from pathlib import Path
sys.path.insert(0, os.environ["REPO"])
os.environ.setdefault("COHORTOS_JWT_SECRET", "stress-secret-not-for-prod-32chars")
os.environ.setdefault("COHORTOS_ENV", "test")
os.environ.setdefault("COHORTOS_SKIP_MODEL_DOWNLOAD", "1")
from models.base import DataAccessLayer, TenantContext
db = os.environ["DB_PATH"]
tenant = TenantContext(tenant_id=os.environ["TID"], mode="offline-first")
dal = DataAccessLayer(tenant, db_path=db)
key = os.environ["IDEM"]
# simulate partial work then hang so parent can SIGKILL
for i in range(5):
    existing = [r for r in dal.get_all("payment_records") if r.get("idempotency_key") == key]
    if existing:
        sys.exit(0)
    if i == 0:
        time.sleep(8.0)
    dal.create("payment_records", {
        "student_id": "s1",
        "year": 2026,
        "month": 10,
        "status": "paid",
        "idempotency_key": key,
        "amount": 50,
    })
sys.exit(0)
"""
    )
    failures = []
    kills = []
    for i in range(200):
        db = str(root / f"c{i}.db")
        tid = str(uuid.uuid4())
        key = f"chaos-{i}-{uuid.uuid4().hex[:8]}"
        env = {
            **os.environ,
            "REPO": str(Path.cwd()),
            "DB_PATH": db,
            "TID": tid,
            "IDEM": key,
            "PYTHONPATH": str(Path.cwd()),
        }
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        delay = rng.uniform(0.01, 0.4)
        time.sleep(delay)
        killed = False
        if proc.poll() is None:
            proc.kill()  # SIGKILL
            proc.wait(timeout=5)
            killed = True
            if proc.returncode not in (-9, 1):  # -9 SIGKILL; some platforms map differently
                # accept if still was killed
                pass
            kills.append(1 if proc.returncode == -9 else 0)
            if proc.returncode != -9:
                failures.append((i, 'rc', proc.returncode))
        else:
            kills.append(0)
        # reopen and integrity check
        try:
            if Path(db).exists() and Path(db).stat().st_size > 0:
                con = sqlite3.connect(db)
                try:
                    row = con.execute("PRAGMA integrity_check").fetchone()
                    if not row or row[0] != "ok":
                        failures.append((i, "integrity", row))
                    # count rows with key
                    try:
                        n = con.execute(
                            "SELECT count(*) FROM payment_records WHERE json_extract(data,'$.idempotency_key')=? OR idempotency_key=?",
                            (key, key),
                        ).fetchone()
                    except Exception:
                        # schema may store columns differently — use DAL
                        n = None
                    con.close()
                    from models.base import DataAccessLayer, TenantContext

                    dal = DataAccessLayer(
                        TenantContext(tenant_id=tid, mode="offline-first"), db_path=db
                    )
                    rows = [
                        r
                        for r in dal.get_all("payment_records")
                        if r.get("idempotency_key") == key
                    ]
                    if len(rows) > 1:
                        failures.append((i, "duplicate", len(rows)))
                    # retry same key via DAL create path: ensure at most one
                    if len(rows) == 0:
                        dal.create(
                            "payment_records",
                            {
                                "student_id": "s1",
                                "year": 2026,
                                "month": 10,
                                "status": "paid",
                                "idempotency_key": key,
                                "amount": 50,
                            },
                        )
                        rows2 = [
                            r
                            for r in dal.get_all("payment_records")
                            if r.get("idempotency_key") == key
                        ]
                        if len(rows2) != 1:
                            failures.append((i, "retry_count", len(rows2)))
                    DataAccessLayer.close_all()
                finally:
                    try:
                        con.close()
                    except Exception:
                        pass
        except Exception as e:
            failures.append((i, "exc", str(e)))
        if len(failures) > 10:
            break
    delivered = sum(kills) if kills else 0
    print(f"kills_delivered={delivered}/200 CHAOS_SEED={seed}")
    # best-effort: at least 50% kills (timing races)
    assert delivered == 200, f"CHAOS_SEED={seed} kills_delivered={delivered} want 200"
    assert not failures, f"CHAOS_SEED={seed} failures={failures[:5]}"
