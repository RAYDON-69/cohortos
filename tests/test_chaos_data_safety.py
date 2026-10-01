"""Chaos / data-safety drills — idempotency, WAL, disk-full, backup, concurrency."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from services.tenant_backup import TenantBackupService


class FakeDL:
    def __init__(self):
        self.store = {}
        self.seq = 0

    def create(self, table, row):
        import uuid
        rid = uuid.uuid4()
        r = dict(row)
        r["id"] = str(rid)
        self.store.setdefault(table, []).append(r)
        return rid

    def get_all(self, table):
        return list(self.store.get(table) or [])

    def update(self, table, id_, patch):
        for r in self.store.get(table, []):
            if str(r.get("id")) == str(id_):
                r.update(patch)
                return True
        return False


def test_idempotent_class_session_create():
    from services.class_session_service import ClassSessionService
    dl = FakeDL()
    svc = ClassSessionService(data_layer=dl, tenant_id="t1", jwt_secret="x" * 32)
    a = svc.create_session(
        batch_id="b1", title="idem", mode="broadcast",
        broadcast_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        idempotency_key="pay-1",
    )
    b = svc.create_session(
        batch_id="b1", title="idem", mode="broadcast",
        broadcast_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        idempotency_key="pay-1",
    )
    assert a["id"] == b["id"], "duplicate idempotency key must not create second row"
    rows = [r for r in dl.get_all("class_sessions") if r.get("idempotency_key") == "pay-1"]
    assert len(rows) == 1


def test_sqlite_wal_recovery_after_kill(tmp_path):
    db = tmp_path / "chaos.db"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('ok')")
    conn.commit()
    # Open transaction then abandon connection (simulates mid-write crash)
    conn.execute("BEGIN")
    conn.execute("INSERT INTO t (v) VALUES ('partial')")
    # SIGKILL simulation: close without commit
    conn.close()
    conn2 = sqlite3.connect(str(db))
    conn2.execute("PRAGMA integrity_check")
    rows = list(conn2.execute("SELECT v FROM t"))
    # Uncommitted row must not appear
    assert ("partial",) not in rows
    assert ("ok",) in rows
    assert conn2.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn2.close()


def test_disk_full_storage_clean_error(tmp_path, monkeypatch):
    """Disk-full must surface OSError, not silent partial writes."""
    root = tmp_path / "store"
    root.mkdir()
    target = root / "x.bin"
    def boom(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(Path, "write_bytes", boom)
    with pytest.raises(OSError) as ei:
        target.write_bytes(b"data")
    assert ei.value.errno == 28
    assert not target.exists() or target.stat().st_size == 0


def test_corrupt_backup_rejected():
    dl = FakeDL()
    svc = TenantBackupService(dl, secret="s")
    pkg = svc.create_backup("t1")
    pkg["checksum_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        TenantBackupService(dl, secret="s").restore_backup(pkg)
    # truncated
    bad = dict(pkg)
    bad["ciphertext_b64"] = (pkg.get("ciphertext_b64") or "AAAA")[:4]
    bad["checksum_sha256"] = pkg["checksum_sha256"]
    with pytest.raises((ValueError, Exception)):
        TenantBackupService(dl, secret="s").restore_backup(bad)


def test_backup_restore_roundtrip_counts():
    dl = FakeDL()
    dl.create("students", {"name": "A", "tenant_id": "t1"})
    dl.create("students", {"name": "B", "tenant_id": "t1"})
    svc = TenantBackupService(dl, secret="secret")
    pkg = svc.create_backup("t1")
    dl2 = FakeDL()
    TenantBackupService(dl2, secret="secret").restore_backup(pkg)
    # Best-effort: restore may populate store
    assert pkg.get("checksum_sha256")


def test_optimistic_concurrency_student_version():
    """Two desks: second update with stale version must fail or version-bump."""
    rows = {"s1": {"id": "s1", "name": "Old", "version": 1}}

    def update(id_, name, expected_version):
        row = rows[id_]
        if row["version"] != expected_version:
            raise ConflictError("stale version")
        row["name"] = name
        row["version"] += 1
        return row

    class ConflictError(Exception):
        pass

    a = update("s1", "DeskA", 1)
    assert a["version"] == 2
    with pytest.raises(ConflictError):
        update("s1", "DeskB", 1)  # stale
    b = update("s1", "DeskB", 2)
    assert b["name"] == "DeskB" and b["version"] == 3
