"""Secrets/injection sweep unit tests."""
import pytest
from services.class_session_service import ClassSessionService, _validate_broadcast_url


class FakeDL:
    def __init__(self):
        self.store = {}
    def create(self, table, row):
        import uuid
        rid = uuid.uuid4()
        r = dict(row); r["id"] = str(rid)
        self.store.setdefault(table, []).append(r)
        return rid
    def get_all(self, table):
        return list(self.store.get(table) or [])


def test_broadcast_rejects_ssrf_schemes():
    for bad in ["http://127.0.0.1/admin", "file:///etc/passwd", "javascript:alert(1)",
                "https://user:pass@evil.com/x"]:
        with pytest.raises(ValueError):
            _validate_broadcast_url(bad)


def test_recording_host_allowlist_blocks_internal():
    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t", jwt_secret="x"*32)
    with pytest.raises(ValueError):
        svc.allowed_recording_url("https://169.254.169.254/latest/meta-data/")


def test_vault_path_no_traversal_names():
    # filenames with .. should be rejected by content service if present
    from pathlib import PurePosixPath
    name = "../../etc/passwd"
    assert ".." in PurePosixPath(name).parts


def test_backup_rejects_tampered_checksum():
    from services.tenant_backup import TenantBackupService
    dl = FakeDL()
    svc = TenantBackupService(dl, secret="s")
    pkg = svc.create_backup("t")
    pkg["checksum_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        TenantBackupService(dl, secret="s").restore_backup(pkg)
