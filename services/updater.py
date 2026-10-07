"""Ed25519-signed update manifest + checksum verify (P37 A4).

OS code signing still requires paid certs — see docs/UPDATER_AND_SIGNING.md.
"""
from __future__ import annotations
import hashlib
import json
import base64
from dataclasses import dataclass
from typing import Optional
from services.licence_service import HAS_CRYPTO, LicenceError

if HAS_CRYPTO:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

@dataclass
class UpdateManifest:
    version: str
    url: str
    sha256: str
    min_version: str  # reject install if current < min (policy) / reject downgrade if version < current
    released_at: str

    def to_dict(self):
        return {
            "version": self.version,
            "url": self.url,
            "sha256": self.sha256,
            "min_version": self.min_version,
            "released_at": self.released_at,
        }

def _pad(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def sign_manifest(priv_raw: bytes, manifest: UpdateManifest) -> str:
    if not HAS_CRYPTO:
        raise LicenceError("cryptography required")
    payload = base64.urlsafe_b64encode(json.dumps(manifest.to_dict(), sort_keys=True).encode()).decode().rstrip("=")
    sig = Ed25519PrivateKey.from_private_bytes(priv_raw).sign(payload.encode("ascii"))
    return f"{payload}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"

def verify_manifest(pub_raw: bytes, token: str) -> UpdateManifest:
    if not HAS_CRYPTO:
        raise LicenceError("cryptography required")
    if "." not in token:
        raise LicenceError("malformed manifest")
    payload_b64, sig_b64 = token.split(".", 1)
    try:
        Ed25519PublicKey.from_public_bytes(pub_raw).verify(_pad(sig_b64), payload_b64.encode("ascii"))
    except Exception as e:
        raise LicenceError(f"bad manifest signature: {e}") from e
    data = json.loads(_pad(payload_b64).decode())
    return UpdateManifest(**{k: data[k] for k in ("version", "url", "sha256", "min_version", "released_at")})

def check_downgrade(current: str, candidate: str) -> None:
    def parts(v):
        return tuple(int(x) for x in v.split(".")[:3])
    if parts(candidate) < parts(current):
        raise LicenceError(f"downgrade blocked: {candidate} < {current}")

def verify_binary_sha256(data: bytes, expected_hex: str) -> None:
    got = hashlib.sha256(data).hexdigest()
    if got != expected_hex.lower():
        raise LicenceError(f"checksum mismatch: {got} != {expected_hex}")

def apply_update_policy(*, pub_raw: bytes, manifest_token: str, current_version: str,
                       binary: Optional[bytes] = None, user_confirmed: bool = False) -> UpdateManifest:
    m = verify_manifest(pub_raw, manifest_token)
    check_downgrade(current_version, m.version)
    if not user_confirmed:
        raise LicenceError("user confirmation required")
    if binary is not None:
        if len(binary) == 0:
            raise LicenceError("truncated download")
        verify_binary_sha256(binary, m.sha256)
    return m
