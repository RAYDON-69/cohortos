from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from services.licence_service import HAS_CRYPTO, generate_keypair, LicenceError
from services.revocation import sign_revocation_list, verify_revocation_list, RevocationCache

pytestmark = pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography required")

@pytest.fixture
def keys():
    return generate_keypair()

def test_forged_list_rejected(keys):
    priv, pub = keys
    tok = sign_revocation_list(priv, ["t1"], expires_at=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat())
    with pytest.raises(LicenceError):
        verify_revocation_list(pub, tok[:-4]+"XXXX")

def test_expired_list(keys):
    priv, pub = keys
    tok = sign_revocation_list(priv, ["t1"], expires_at=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat())
    with pytest.raises(LicenceError):
        verify_revocation_list(pub, tok)

def test_cache_enforces_revocation(keys, tmp_path):
    priv, pub = keys
    tok = sign_revocation_list(priv, ["bad-tenant"], expires_at=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat())
    cache = RevocationCache(tmp_path / "rev.json", pub)
    cache.store(tok)
    assert cache.is_revoked("bad-tenant") is True
    assert cache.is_revoked("good-tenant") is False

def test_offline_30_days(keys, tmp_path):
    priv, pub = keys
    tok = sign_revocation_list(priv, ["t1"], expires_at=(datetime.now(timezone.utc)+timedelta(days=60)).isoformat())
    cache = RevocationCache(tmp_path / "rev.json", pub, offline_max_days=30)
    cache.store(tok)
    doc = __import__("json").loads((tmp_path/"rev.json").read_text())
    doc["fetched_at"] = (datetime.now(timezone.utc)-timedelta(days=31)).isoformat()
    (tmp_path/"rev.json").write_text(__import__("json").dumps(doc))
    with pytest.raises(LicenceError):
        cache.is_revoked("t1")
