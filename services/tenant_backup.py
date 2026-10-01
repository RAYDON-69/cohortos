"""Encrypted tenant backup / restore / PDPA export (P27)."""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def derive_fernet(secret: str) -> Fernet:
    # Stable 32-byte url-safe key from secret
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    import base64
    return Fernet(base64.urlsafe_b64encode(digest))


class TenantBackupService:
    def __init__(self, data_layer=None, vault_root: Optional[str] = None, secret: Optional[str] = None):
        self.data_layer = data_layer
        self.vault_root = Path(vault_root or os.environ.get("COHORTOS_STORAGE_ROOT") or "/tmp/cohortos-storage")
        self.secret = secret or os.environ.get("COHORTOS_JWT_SECRET") or "dev-backup-secret"

    def _tables_snapshot(self) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        if not self.data_layer:
            return out
        # Prefer list_tables if present; else common tables
        names = [
            "students", "batches", "attendance_records", "payment_records",
            "class_sessions", "class_session_notices", "voice_call_scripts",
            "voice_call_summaries", "call_desk_outcomes", "content_resources",
            "accounts", "ai_chat_turns",
        ]
        for n in names:
            try:
                rows = self.data_layer.get_all(n) or []
                out[n] = list(rows)
            except Exception:
                out[n] = []
        return out

    def create_backup(self, tenant_id: str) -> Dict[str, Any]:
        payload = {
            "version": 1,
            "tenant_id": tenant_id,
            "created_at": _now(),
            "tables": self._tables_snapshot(),
            "vault_index": [],
        }
        # vault file names only (not full blobs in unit tests)
        vdir = self.vault_root / tenant_id
        if vdir.is_dir():
            payload["vault_index"] = [p.name for p in vdir.rglob("*") if p.is_file()][:5000]

        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        checksum = hashlib.sha256(raw).hexdigest()
        token = derive_fernet(self.secret).encrypt(raw)
        return {
            "tenant_id": tenant_id,
            "checksum_sha256": checksum,
            "ciphertext_b64": __import__("base64").b64encode(token).decode("ascii"),
            "created_at": payload["created_at"],
            "bytes": len(token),
        }

    def restore_backup(self, package: Dict[str, Any], *, into_empty: bool = True) -> Dict[str, Any]:
        if not self.data_layer:
            raise RuntimeError("no data_layer")
        token = __import__("base64").b64decode(package["ciphertext_b64"])
        try:
            raw = derive_fernet(self.secret).decrypt(token)
        except InvalidToken as e:
            raise ValueError("decrypt_failed") from e
        checksum = hashlib.sha256(raw).hexdigest()
        if package.get("checksum_sha256") and package["checksum_sha256"] != checksum:
            raise ValueError("checksum_mismatch")
        payload = json.loads(raw.decode("utf-8"))
        restored = 0
        for table, rows in (payload.get("tables") or {}).items():
            for row in rows:
                try:
                    # Prefer create; id will be reassigned — acceptable for restore-into-empty
                    self.data_layer.create(table, dict(row))
                    restored += 1
                except Exception:
                    continue
        return {
            "tenant_id": payload.get("tenant_id"),
            "restored_rows": restored,
            "checksum_ok": True,
            "vault_index_count": len(payload.get("vault_index") or []),
        }

    def export_pdpa(self, tenant_id: str) -> Dict[str, Any]:
        """JSON export for subject-access requests (no ciphertext)."""
        snap = self._tables_snapshot()
        return {
            "tenant_id": tenant_id,
            "exported_at": _now(),
            "label": "PDPA export — not legal advice",
            "tables": snap,
        }
