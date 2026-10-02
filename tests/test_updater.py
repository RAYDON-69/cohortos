import hashlib
import pytest
from services.licence_service import HAS_CRYPTO, generate_keypair, LicenceError
from services.updater import (
    UpdateManifest, sign_manifest, verify_manifest, apply_update_policy, check_downgrade, verify_binary_sha256,
)

pytestmark = pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography required")

@pytest.fixture
def keys():
    return generate_keypair()

def _man(version="1.2.0", sha=None):
    data = b"fake-installer-bytes"
    return UpdateManifest(
        version=version,
        url="https://example.com/app.bin",
        sha256=sha or hashlib.sha256(data).hexdigest(),
        min_version="1.0.0",
        released_at="2026-10-01T00:00:00+00:00",
    ), data

def test_sign_verify(keys):
    priv, pub = keys
    m, _ = _man()
    tok = sign_manifest(priv, m)
    assert verify_manifest(pub, tok).version == "1.2.0"

def test_tampered_manifest(keys):
    priv, pub = keys
    m, _ = _man()
    tok = sign_manifest(priv, m)
    bad = tok[:-6] + "ZZZZZZ"
    with pytest.raises(LicenceError):
        verify_manifest(pub, bad)

def test_wrong_key(keys):
    priv, _ = keys
    _, pub2 = generate_keypair()
    m, _ = _man()
    tok = sign_manifest(priv, m)
    with pytest.raises(LicenceError):
        verify_manifest(pub2, tok)

def test_downgrade_blocked(keys):
    with pytest.raises(LicenceError):
        check_downgrade("1.2.0", "1.1.9")

def test_corrupt_binary(keys):
    priv, pub = keys
    m, data = _man()
    tok = sign_manifest(priv, m)
    with pytest.raises(LicenceError):
        apply_update_policy(pub_raw=pub, manifest_token=tok, current_version="1.0.0",
                            binary=data + b"x", user_confirmed=True)

def test_truncated_download(keys):
    priv, pub = keys
    m, data = _man()
    tok = sign_manifest(priv, m)
    with pytest.raises(LicenceError):
        apply_update_policy(pub_raw=pub, manifest_token=tok, current_version="1.0.0",
                            binary=b"", user_confirmed=True)

def test_replay_old_manifest_downgrade(keys):
    priv, pub = keys
    m, data = _man(version="1.0.0")
    tok = sign_manifest(priv, m)
    with pytest.raises(LicenceError):
        apply_update_policy(pub_raw=pub, manifest_token=tok, current_version="1.2.0",
                            binary=data, user_confirmed=True)

def test_happy_path(keys):
    priv, pub = keys
    m, data = _man(version="1.3.0")
    tok = sign_manifest(priv, m)
    out = apply_update_policy(pub_raw=pub, manifest_token=tok, current_version="1.2.0",
                              binary=data, user_confirmed=True)
    assert out.version == "1.3.0"
