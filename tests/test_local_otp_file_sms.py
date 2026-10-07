"""Local file SMS provider for laptop installs without Twilio."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path


def test_local_file_sms_writes_otp_latest():
    from services.sms_provider import build_sms_provider, LocalFileSmsProvider

    td = Path(tempfile.mkdtemp())
    path = str(td / "otp_log.txt")
    os.environ["COHORTOS_LOCAL_OTP_FILE"] = path
    # clear twilio
    for k in ("COHORTOS_TWILIO_ACCOUNT_SID", "COHORTOS_TWILIO_AUTH_TOKEN", "COHORTOS_TWILIO_FROM"):
        os.environ.pop(k, None)
    p = build_sms_provider({})
    assert isinstance(p, LocalFileSmsProvider)
    p.send("01710000001", "Your code is 123456")
    assert Path(path).exists()
    latest = td / "otp_latest.txt"
    assert latest.exists()
    assert "123456" in latest.read_text()
