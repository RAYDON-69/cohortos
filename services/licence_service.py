"""Signed licence tokens + offline grace + clock-rollback detection (P36 C1).

Public key ships in the app; private key never does.
Honest limit: offline desktop can be cracked; goal is casual-misuse resistance.
"""
from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Optional cryptography — tests generate ephemeral keys
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

GRACE_DAYS = 7
CLOCK_ROLLBACK_HOURS = 24
HIGHWATER_PATH_ENV = "COHORTOS_LICENCE_HIGHWATER"


@dataclass
class LicenceClaims:
    tenant_id: str
    plan: str
    exp: str  # ISO expiry
    seats: int
    issued_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "plan": self.plan,
            "exp": self.exp,
            "seats": self.seats,
            "issued_at": self.issued_at,
        }


class LicenceError(Exception):
    pass


def generate_keypair() -> Tuple[bytes, bytes]:
    """Return (private_raw_32, public_raw_32). Private never ships in app."""
    if not HAS_CRYPTO:
        raise LicenceError("cryptography package required")
    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv_bytes, pub_bytes


def sign_licence(priv_raw: bytes, claims: LicenceClaims) -> str:
    if not HAS_CRYPTO:
        raise LicenceError("cryptography package required")
    payload = base64.urlsafe_b64encode(json.dumps(claims.to_dict(), sort_keys=True).encode()).decode().rstrip("=")
    priv = Ed25519PrivateKey.from_private_bytes(priv_raw)
    sig = priv.sign(payload.encode("ascii"))
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{payload}.{sig_b64}"


def verify_licence(pub_raw: bytes, token: str, *, now: Optional[datetime] = None) -> LicenceClaims:
    if not HAS_CRYPTO:
        raise LicenceError("cryptography package required")
    if "." not in token:
        raise LicenceError("malformed token")
    payload_b64, sig_b64 = token.split(".", 1)
    # pad
    def pad(s: str) -> bytes:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    try:
        pub = Ed25519PublicKey.from_public_bytes(pub_raw)
        pub.verify(pad(sig_b64), payload_b64.encode("ascii"))
    except Exception as e:
        raise LicenceError(f"bad signature: {e}") from e
    try:
        data = json.loads(pad(payload_b64).decode())
    except Exception as e:
        raise LicenceError(f"bad payload: {e}") from e
    required = ("tenant_id", "plan", "exp", "seats", "issued_at")
    if any(k not in data for k in required):
        raise LicenceError("missing claims")
    return LicenceClaims(
        tenant_id=str(data["tenant_id"]),
        plan=str(data["plan"]),
        exp=str(data["exp"]),
        seats=int(data["seats"]),
        issued_at=str(data["issued_at"]),
    )


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def licence_status(
    claims: LicenceClaims,
    *,
    now: Optional[datetime] = None,
    highwater: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return mode: active | grace | read_only | reject_clock."""
    now = now or datetime.now(timezone.utc)
    if highwater and (highwater - now) > timedelta(hours=CLOCK_ROLLBACK_HOURS):
        return {
            "mode": "reject_clock",
            "message_en": "System clock moved backward. Re-verify licence online.",
            "message_bn": "সিস্টেম ঘড়ি পেছনে গেছে। লাইসেন্স আবার যাচাই করুন।",
            "writable": False,
        }
    exp = _parse_iso(claims.exp)
    if now <= exp:
        return {"mode": "active", "writable": True, "message_en": "", "message_bn": ""}
    grace_end = exp + timedelta(days=GRACE_DAYS)
    if now <= grace_end:
        return {
            "mode": "grace",
            "writable": True,
            "grace_days_left": (grace_end - now).days,
            "message_en": "Licence expired — grace period active.",
            "message_bn": "লাইসেন্সের মেয়াদ শেষ — গ্রেস পিরিয়ড চলছে।",
        }
    return {
        "mode": "read_only",
        "writable": False,
        "message_en": "Subscription lapsed. View, export and backup only. Renew to continue writing.",
        "message_bn": "সাবস্ক্রিপশন শেষ। শুধু দেখা, এক্সপোর্ট ও ব্যাকআপ। লিখতে রিনিউ করুন।",
    }


def highwater_path() -> Path:
    p = os.environ.get(HIGHWATER_PATH_ENV)
    if p:
        return Path(p)
    return Path(os.environ.get("TMPDIR") or "/tmp") / "cohortos-licence-highwater.txt"


def touch_highwater(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    path = highwater_path()
    prev = None
    if path.exists():
        try:
            prev = _parse_iso(path.read_text().strip())
        except Exception:
            prev = None
    if prev and prev > now:
        return prev  # do not move backward
    path.write_text(now.isoformat())
    return now


def load_highwater() -> Optional[datetime]:
    path = highwater_path()
    if not path.exists():
        return None
    try:
        return _parse_iso(path.read_text().strip())
    except Exception:
        return None
