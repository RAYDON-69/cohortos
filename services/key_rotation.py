"""Fernet multi-key rotation with rollback (P36 C3)."""
from __future__ import annotations
import os
from typing import List, Optional
from cryptography.fernet import Fernet, MultiFernet, InvalidToken

ENV_KEYS = "COHORTOS_FERNET_KEYS"  # comma-separated, newest first

def load_fernets(keys_csv: Optional[str] = None) -> MultiFernet:
    raw = keys_csv if keys_csv is not None else os.environ.get(ENV_KEYS, "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        # derive from JWT secret for dev only
        import base64, hashlib
        secret = os.environ.get("COHORTOS_JWT_SECRET") or "dev-only-not-for-prod"
        digest = hashlib.sha256(secret.encode()).digest()
        parts = [base64.urlsafe_b64encode(digest).decode()]
    return MultiFernet([Fernet(k.encode() if isinstance(k, str) else k) for k in parts])

def encrypt(plain: str, keys_csv: Optional[str] = None) -> str:
    return load_fernets(keys_csv).encrypt(plain.encode("utf-8")).decode("ascii")

def decrypt(token: str, keys_csv: Optional[str] = None) -> str:
    return load_fernets(keys_csv).decrypt(token.encode("ascii")).decode("utf-8")

def rotate(ciphertexts: List[str], old_keys_csv: str, new_key: str) -> List[str]:
    """Decrypt with old keyring, re-encrypt with new_key first in chain."""
    old = load_fernets(old_keys_csv)
    # new MultiFernet: new key first, then old keys for decrypt fallback
    chain = new_key + "," + old_keys_csv
    new_mf = load_fernets(chain)
    out = []
    for c in ciphertexts:
        plain = old.decrypt(c.encode("ascii"))
        out.append(new_mf.encrypt(plain).decode("ascii"))
    return out
