"""Signed revocation list from static host (P37 A5). Zero server cost."""
from __future__ import annotations
import json, base64, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from services.licence_service import HAS_CRYPTO, LicenceError

if HAS_CRYPTO:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

def _pad(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def sign_revocation_list(priv_raw: bytes, revoked_tenant_ids: List[str], *,
                         expires_at: str, issued_at: Optional[str] = None) -> str:
    if not HAS_CRYPTO:
        raise LicenceError("cryptography required")
    payload_obj = {
        "revoked": sorted(set(revoked_tenant_ids)),
        "expires_at": expires_at,
        "issued_at": issued_at or datetime.now(timezone.utc).isoformat(),
    }
    payload = base64.urlsafe_b64encode(json.dumps(payload_obj, sort_keys=True).encode()).decode().rstrip("=")
    sig = Ed25519PrivateKey.from_private_bytes(priv_raw).sign(payload.encode("ascii"))
    return f"{payload}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"

def verify_revocation_list(pub_raw: bytes, token: str, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    if not HAS_CRYPTO:
        raise LicenceError("cryptography required")
    now = now or datetime.now(timezone.utc)
    if "." not in token:
        raise LicenceError("malformed revocation list")
    payload_b64, sig_b64 = token.split(".", 1)
    try:
        Ed25519PublicKey.from_public_bytes(pub_raw).verify(_pad(sig_b64), payload_b64.encode("ascii"))
    except Exception as e:
        raise LicenceError(f"forged revocation list: {e}") from e
    data = json.loads(_pad(payload_b64).decode())
    exp = datetime.fromisoformat(str(data["expires_at"]).replace("Z", "+00:00"))
    if now > exp:
        raise LicenceError("revocation list expired")
    return data

class RevocationCache:
    def __init__(self, path: Path, pub_raw: bytes, offline_max_days: int = 30):
        self.path = path
        self.pub_raw = pub_raw
        self.offline_max_days = offline_max_days

    def store(self, token: str) -> None:
        data = verify_revocation_list(self.pub_raw, token)
        self.path.write_text(json.dumps({"token": token, "fetched_at": datetime.now(timezone.utc).isoformat(), "data": data}))

    def is_revoked(self, tenant_id: str, *, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if not self.path.exists():
            return False
        doc = json.loads(self.path.read_text())
        fetched = datetime.fromisoformat(doc["fetched_at"].replace("Z", "+00:00"))
        if (now - fetched).days > self.offline_max_days:
            # stale cache → fail closed to read-only via caller
            raise LicenceError("revocation cache offline too long")
        # re-verify stored token
        data = verify_revocation_list(self.pub_raw, doc["token"], now=now)
        return tenant_id in set(data.get("revoked") or [])
