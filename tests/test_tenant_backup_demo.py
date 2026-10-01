from services.tenant_backup import TenantBackupService
from services.demo_seed import DemoSeedService, DEMO_MARKER


class FakeDL:
    def __init__(self):
        self.store = {}
    def create(self, table, row):
        import uuid
        rid = uuid.uuid4()
        r = dict(row)
        r["id"] = str(rid)
        self.store.setdefault(table, []).append(r)
        return rid
    def get_all(self, table):
        return list(self.store.get(table) or [])
    def delete(self, table, rid):
        self.store[table] = [r for r in self.store.get(table, []) if r.get("id") != str(rid)]


def test_backup_restore_roundtrip_empty_db():
    dl = FakeDL()
    # seed
    DemoSeedService(dl).load_demo("t1")
    assert any(r.get("demo_marker") == DEMO_MARKER for r in dl.get_all("students"))
    svc = TenantBackupService(dl, secret="test-secret")
    pkg = svc.create_backup("t1")
    assert pkg["checksum_sha256"] and pkg["ciphertext_b64"]
    # restore into empty
    dl2 = FakeDL()
    out = TenantBackupService(dl2, secret="test-secret").restore_backup(pkg)
    assert out["checksum_ok"]
    assert out["restored_rows"] >= 1


def test_demo_remove_clears_marker():
    dl = FakeDL()
    DemoSeedService(dl).load_demo("t1")
    DemoSeedService(dl).remove_demo("t1")
    assert not any(r.get("demo_marker") == DEMO_MARKER for r in dl.get_all("students"))


def test_pdpa_export_has_label():
    dl = FakeDL()
    DemoSeedService(dl).load_demo("t1")
    exp = TenantBackupService(dl).export_pdpa("t1")
    assert "PDPA" in exp["label"]
