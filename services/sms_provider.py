"""SMS provider — Twilio when credentials present; otherwise explicit not-configured."""
from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional
from services.safe_http import safe_urlopen


class SmsNotConfiguredError(RuntimeError):
    pass


class SmsProvider:
    def send(self, to_phone: str, body: str) -> Dict[str, Any]:
        raise NotImplementedError


class TwilioSmsProvider(SmsProvider):
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number

    def send(self, to_phone: str, body: str) -> Dict[str, Any]:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = urllib.parse.urlencode({
            "To": to_phone,
            "From": self.from_number,
            "Body": body,
        }).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        token = f"{self.account_sid}:{self.auth_token}".encode()
        import base64
        req.add_header("Authorization", "Basic " + base64.b64encode(token).decode())
        with safe_urlopen(  # nosec B310 — URL from configured HTTPS provider endpoint
            req, timeout=30) as resp:
            out = json.loads(resp.read().decode())
        return {"ok": True, "provider": "twilio", "sid": out.get("sid"), "status": out.get("status"), "raw": out}



class LocalFileSmsProvider(SmsProvider):
    """Write OTP messages to a local file (laptop installs without Twilio)."""

    def __init__(self, path: str):
        self.path = path

    def send(self, to_phone: str, body: str) -> Dict[str, Any]:
        import datetime
        from pathlib import Path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        line = f"{datetime.datetime.now(datetime.timezone.utc).isoformat()}\tto={to_phone}\t{body}\n"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
        # also write latest-only for CLI helpers
        latest = Path(self.path).with_name("otp_latest.txt")
        latest.write_text(body + "\n", encoding="utf-8")
        return {"ok": True, "provider": "local_file", "path": self.path}


def build_sms_provider(config: Optional[Dict[str, Any]] = None) -> SmsProvider:
    cfg = config or {}
    sid = cfg.get("twilio_account_sid") or os.environ.get("COHORTOS_TWILIO_ACCOUNT_SID")
    token = cfg.get("twilio_auth_token") or os.environ.get("COHORTOS_TWILIO_AUTH_TOKEN")
    from_n = cfg.get("twilio_from") or os.environ.get("COHORTOS_TWILIO_FROM")
    if sid and token and from_n:
        return TwilioSmsProvider(sid, token, from_n)
    local_path = cfg.get("local_otp_file") or os.environ.get("COHORTOS_LOCAL_OTP_FILE")
    if local_path:
        return LocalFileSmsProvider(local_path)
    raise SmsNotConfiguredError(
        "SMS not configured. Set COHORTOS_TWILIO_* or COHORTOS_LOCAL_OTP_FILE for laptop installs."
    )
