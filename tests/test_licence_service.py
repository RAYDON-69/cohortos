from __future__ import annotations
from datetime import datetime, timedelta, timezone
import pytest
from services.licence_service import (
    HAS_CRYPTO, LicenceClaims, LicenceError, generate_keypair, sign_licence,
    verify_licence, licence_status, touch_highwater, load_highwater, highwater_path,
)

pytestmark = pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography required")

@pytest.fixture
def keys(tmp_path, monkeypatch):
    monkeypatch.setenv("COHORTOS_LICENCE_HIGHWATER", str(tmp_path / "hw.txt"))
    return generate_keypair()

def _claims(exp_delta_days=30, seats=100):
    now = datetime.now(timezone.utc)
    return LicenceClaims(
        tenant_id="tenant-a",
        plan="growth",
        exp=(now + timedelta(days=exp_delta_days)).isoformat(),
        seats=seats,
        issued_at=now.isoformat(),
    )

def test_sign_verify_roundtrip(keys):
    priv, pub = keys
    tok = sign_licence(priv, _claims())
    c = verify_licence(pub, tok)
    assert c.tenant_id == "tenant-a"
    assert c.plan == "growth"

def test_tamper_rejected(keys):
    priv, pub = keys
    tok = sign_licence(priv, _claims())
    bad = tok[:-4] + ("AAAA" if not tok.endswith("AAAA") else "BBBB")
    with pytest.raises(LicenceError):
        verify_licence(pub, bad)

def test_active_writable(keys):
    st = licence_status(_claims(30))
    assert st["mode"] == "active" and st["writable"] is True

def test_grace_then_readonly(keys):
    st = licence_status(_claims(-3))  # expired 3 days ago → grace
    assert st["mode"] == "grace" and st["writable"] is True
    st2 = licence_status(_claims(-10))  # past grace
    assert st2["mode"] == "read_only" and st2["writable"] is False
    assert "রিনিউ" in st2["message_bn"] or "Renew" in st2["message_en"]

def test_clock_rollback_detected(keys, tmp_path, monkeypatch):
    monkeypatch.setenv("COHORTOS_LICENCE_HIGHWATER", str(tmp_path / "hw.txt"))
    future = datetime.now(timezone.utc) + timedelta(days=2)
    touch_highwater(future)
    hw = load_highwater()
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    st = licence_status(_claims(30), now=past, highwater=hw)
    assert st["mode"] == "reject_clock"
    assert st["writable"] is False

def test_highwater_monotonic(keys, tmp_path, monkeypatch):
    monkeypatch.setenv("COHORTOS_LICENCE_HIGHWATER", str(tmp_path / "hw.txt"))
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t0 = datetime(2025, 12, 1, tzinfo=timezone.utc)
    touch_highwater(t1)
    touch_highwater(t0)  # should not go backward
    assert load_highwater() == t1
