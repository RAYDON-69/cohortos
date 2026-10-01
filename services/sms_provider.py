"""SMS provider — Twilio when credentials present; otherwise explicit not-configured."""
from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


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
        with urllib.request.urlopen(  # nosec B310 — URL from configured HTTPS provider endpoint
            req, timeout=30) as resp:
            out = json.loads(resp.read().decode())
        return {"ok": True, "provider": "twilio", "sid": out.get("sid"), "status": out.get("status"), "raw": out}


def build_sms_provider(config: Optional[Dict[str, Any]] = None) -> SmsProvider:
    cfg = config or {}
    sid = cfg.get("twilio_account_sid") or os.environ.get("COHORTOS_TWILIO_ACCOUNT_SID")
    token = cfg.get("twilio_auth_token") or os.environ.get("COHORTOS_TWILIO_AUTH_TOKEN")
    from_n = cfg.get("twilio_from") or os.environ.get("COHORTOS_TWILIO_FROM")
    if sid and token and from_n:
        return TwilioSmsProvider(sid, token, from_n)
    raise SmsNotConfiguredError(
        "SMS not configured. Set COHORTOS_TWILIO_ACCOUNT_SID, COHORTOS_TWILIO_AUTH_TOKEN, COHORTOS_TWILIO_FROM "
        "or Messaging settings."
    )
