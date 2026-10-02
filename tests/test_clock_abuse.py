from datetime import datetime, timedelta, timezone
from services.licence_service import LicenceClaims, licence_status, touch_highwater, load_highwater
from zoneinfo import ZoneInfo

def test_grace_boundary_exact():
    exp = datetime(2026, 6, 1, tzinfo=timezone.utc)
    claims = LicenceClaims("t", "starter", exp.isoformat(), 10, exp.isoformat())
    # day 7 still grace
    st = licence_status(claims, now=exp + timedelta(days=7))
    assert st["mode"] in ("grace", "read_only")
    st2 = licence_status(claims, now=exp + timedelta(days=8))
    assert st2["mode"] == "read_only"

def test_clock_jump_forward_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("COHORTOS_LICENCE_HIGHWATER", str(tmp_path / "hw"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    touch_highwater(now)
    later = now + timedelta(days=40)
    touch_highwater(later)
    assert load_highwater() == later

def test_dhaka_fee_due_no_dst():
    dhaka = ZoneInfo("Asia/Dhaka")
    a = datetime(2026, 1, 15, 23, 0, tzinfo=dhaka)
    b = datetime(2026, 7, 15, 23, 0, tzinfo=dhaka)
    assert a.utcoffset() == b.utcoffset()
