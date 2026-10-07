"""B4: kill mid-write / corrupt backup / wrong key must not silently succeed."""
from __future__ import annotations
import json
from services.tenant_backup import TenantBackupService
from services.key_rotation import encrypt, decrypt, rotate
from cryptography.fernet import Fernet

class FakeDAL:
    def __init__(self):
        self.store = {"students": [{"id": "s1", "tenant_id": "t1", "name": "A"}]}
    def get_all(self, table):
        return list(self.store.get(table, []))
    def create(self, table, row):
        self.store.setdefault(table, []).append(dict(row))
        return row.get("id")

def test_wrong_fernet_key_restore_fails():
    dal = FakeDAL()
    svc = TenantBackupService(dal, secret="key-one-secret-32chars-xxxxxxxx")
    pkg = svc.create_backup("t1")
    svc2 = TenantBackupService(dal, secret="key-two-secret-32chars-xxxxxxxx")
    try:
        svc2.restore_backup(pkg)
        assert False, "wrong key must not restore"
    except ValueError as e:
        assert "decrypt" in str(e)

def test_corrupt_ciphertext_fails():
    dal = FakeDAL()
    svc = TenantBackupService(dal, secret="backup-test-secret-32chars-xxxx")
    pkg = svc.create_backup("t1")
    pkg["ciphertext_b64"] = "AAAA" + pkg["ciphertext_b64"][4:]
    try:
        svc.restore_backup(pkg)
        assert False
    except ValueError:
        pass

def test_half_rotated_key_still_decrypts_with_chain():
    k1 = Fernet.generate_key().decode()
    k2 = Fernet.generate_key().decode()
    c = encrypt("pii", k1)
    # chain new,old
    assert decrypt(c, f"{k2},{k1}") == "pii"
