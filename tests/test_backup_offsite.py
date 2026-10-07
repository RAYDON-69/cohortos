"""Off-machine encrypted backup → wipe → restore → compare counts (P36 C5)."""
from __future__ import annotations
import json
from pathlib import Path
from services.tenant_backup import TenantBackupService

class FakeDAL:
    def __init__(self):
        self.store = {
            "students": [
                {"id": "s1", "tenant_id": "t1", "name": "A"},
                {"id": "s2", "tenant_id": "t1", "name": "B"},
            ],
            "payment_records": [{"id": "f1", "tenant_id": "t1", "amount": 100}],
        }
    def get_all(self, table):
        return list(self.store.get(table, []))
    def create(self, table, row):
        self.store.setdefault(table, []).append(dict(row))
        return row.get("id")
    def wipe_tenant(self, tenant_id):
        for k in self.store:
            self.store[k] = [r for r in self.store[k] if r.get("tenant_id") != tenant_id]

def test_backup_to_usb_wipe_restore_counts(tmp_path):
    dal = FakeDAL()
    svc = TenantBackupService(dal, secret="backup-test-secret-32chars-xxxx")
    before_students = len(dal.get_all("students"))
    assert before_students == 2
    pkg = svc.create_backup("t1")
    assert "ciphertext_b64" in pkg and pkg["checksum_sha256"]
    dest = tmp_path / "usb" / "cohortos-backup.json"
    dest.parent.mkdir(parents=True)
    dest.write_text(json.dumps(pkg))
    assert dest.stat().st_size > 50
    # power-cut / stolen laptop simulation
    dal.wipe_tenant("t1")
    assert len(dal.get_all("students")) == 0
    # restore drill
    loaded = json.loads(dest.read_text())
    result = svc.restore_backup(loaded, into_empty=True)
    assert result["checksum_ok"] is True
    assert result["restored_rows"] >= 2
    assert len(dal.get_all("students")) >= 2

def test_corrupted_backup_rejected(tmp_path):
    dal = FakeDAL()
    svc = TenantBackupService(dal, secret="backup-test-secret-32chars-xxxx")
    pkg = svc.create_backup("t1")
    pkg["ciphertext_b64"] = pkg["ciphertext_b64"][:-8] + "AAAAAAAA"
    try:
        svc.restore_backup(pkg)
        assert False, "should have raised"
    except ValueError as e:
        assert "decrypt" in str(e) or "checksum" in str(e)
