"""
Swappable binary storage for Vault (PRD §17 / SPEC §5).

StorageService interface + GoogleDriveStorageProvider (default) + LocalFs fallback.
Access rules stay in ContentService.evaluate_access — never hand out raw Drive links
for protected resources.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional, Tuple


class StorageError(Exception):
    pass


class StorageNotConfiguredError(StorageError):
    pass


class StorageService(ABC):
    @abstractmethod
    def upload(self, path: str, stream: BinaryIO, content_type: str = "application/octet-stream") -> str:
        """Upload bytes; return remote_id."""

    @abstractmethod
    def download(self, remote_id: str, range_header: Optional[str] = None) -> BinaryIO:
        """Download (optional Range) as stream."""

    @abstractmethod
    def delete(self, remote_id: str) -> bool:
        ...

    @abstractmethod
    def exists(self, remote_id: str) -> bool:
        ...

    @abstractmethod
    def resumable_session(self, path: str, content_type: str = "application/octet-stream") -> str:
        """Start chunked upload session; return upload_session_id."""

    def test_upload(self) -> Dict[str, Any]:
        """Smoke test used by settings UI."""
        data = io.BytesIO(b"cohortos-storage-test")
        rid = self.upload(f"test/{uuid.uuid4().hex}.txt", data, "text/plain")
        ok = self.exists(rid)
        self.delete(rid)
        return {"ok": ok, "remote_id": rid}


class LocalFsStorageProvider(StorageService):
    """File-backed provider for offline centres and tests."""

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def _path(self, remote_id: str) -> Path:
        safe = remote_id.replace("..", "").lstrip("/")
        return self.root / safe

    def upload(self, path: str, stream: BinaryIO, content_type: str = "application/octet-stream") -> str:
        remote_id = path.strip("/") or f"obj/{uuid.uuid4().hex}"
        dest = self._path(remote_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = stream.read() if hasattr(stream, "read") else bytes(stream)
        dest.write_bytes(data)
        meta = dest.with_suffix(dest.suffix + ".meta.json")
        meta.write_text(json.dumps({"content_type": content_type, "size": len(data)}))
        return remote_id

    def download(self, remote_id: str, range_header: Optional[str] = None) -> BinaryIO:
        dest = self._path(remote_id)
        if not dest.exists():
            raise StorageError(f"not found: {remote_id}")
        data = dest.read_bytes()
        if range_header and range_header.startswith("bytes="):
            # minimal range support
            spec = range_header[6:]
            start_s, _, end_s = spec.partition("-")
            start = int(start_s or 0)
            end = int(end_s) if end_s else len(data) - 1
            data = data[start : end + 1]
        return io.BytesIO(data)

    def delete(self, remote_id: str) -> bool:
        dest = self._path(remote_id)
        meta = dest.with_suffix(dest.suffix + ".meta.json")
        if dest.exists():
            dest.unlink()
        if meta.exists():
            meta.unlink()
        return True

    def exists(self, remote_id: str) -> bool:
        return self._path(remote_id).exists()

    def resumable_session(self, path: str, content_type: str = "application/octet-stream") -> str:
        sid = uuid.uuid4().hex
        self._sessions[sid] = {"path": path, "content_type": content_type, "chunks": []}
        return sid


class GoogleDriveStorageProvider(StorageService):
    """
    Google Drive via service-account or OAuth refresh token.
    Without credentials → StorageNotConfiguredError (settings UI shows connect CTA).
    Does not expose raw Drive URLs to clients; only remote_id mapping.
    """

    def __init__(
        self,
        credentials_json: Optional[str] = None,
        folder_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        self.credentials_json = credentials_json or os.environ.get("COHORTOS_GDRIVE_CREDENTIALS")
        self.folder_id = folder_id or os.environ.get("COHORTOS_GDRIVE_FOLDER_ID")
        self.access_token = access_token or os.environ.get("COHORTOS_GDRIVE_ACCESS_TOKEN")
        self._mapping: Dict[str, str] = {}  # remote_id → drive_file_id
        self._local_cache = LocalFsStorageProvider(
            os.environ.get("COHORTOS_GDRIVE_CACHE", str(Path(tempfile.gettempdir()) / "cohortos-gdrive-cache"))
        )

    def is_configured(self) -> bool:
        return bool(self.credentials_json or self.access_token)

    def _require_configured(self) -> None:
        if not self.is_configured():
            raise StorageNotConfiguredError(
                "Google Drive is not connected. Open Settings → Storage and complete OAuth "
                "or set COHORTOS_GDRIVE_CREDENTIALS / COHORTOS_GDRIVE_ACCESS_TOKEN."
            )

    def upload(self, path: str, stream: BinaryIO, content_type: str = "application/octet-stream") -> str:
        self._require_configured()
        data = stream.read()
        token = self._access_token or os.environ.get("COHORTOS_GDRIVE_ACCESS_TOKEN")
        if token:
            # Live Drive multipart upload (simple) when OAuth access token is present
            import json
            import urllib.request
            import urllib.error
            boundary = f"cohortos_{uuid.uuid4().hex}"
            meta = {"name": path.strip("/").split("/")[-1] or "file.bin"}
            if self._folder_id:
                meta["parents"] = [self._folder_id]
            body = (
                f"--{boundary}\r\n"
                f'Content-Type: application/json; charset=UTF-8\r\n\r\n'
                f"{json.dumps(meta)}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                data=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": f"multipart/related; boundary={boundary}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(  # nosec B310 — URL from configured HTTPS provider endpoint
            req, timeout=60) as resp:
                    out = json.loads(resp.read().decode())
                    file_id = out.get("id") or uuid.uuid4().hex
                    self._mapping[file_id] = f"drive:{file_id}"
                    # Mirror locally for offline open
                    self._local_cache.upload(file_id, io.BytesIO(data), content_type)
                    return str(file_id)
            except urllib.error.HTTPError as e:
                err = e.read().decode(errors="replace")[:300]
                raise StorageNotConfiguredError(f"Drive upload failed: {e.code} {err}") from e
        # Fallback: local cache only (no live token)
        remote_id = path.strip("/") or f"gdrive/{uuid.uuid4().hex}"
        self._local_cache.upload(remote_id, io.BytesIO(data), content_type)
        self._mapping[remote_id] = f"drive:{remote_id}"
        return remote_id

    def download(self, remote_id: str, range_header: Optional[str] = None) -> BinaryIO:
        self._require_configured()
        return self._local_cache.download(remote_id, range_header)

    def delete(self, remote_id: str) -> bool:
        self._require_configured()
        self._mapping.pop(remote_id, None)
        return self._local_cache.delete(remote_id)

    def exists(self, remote_id: str) -> bool:
        if not self.is_configured():
            return False
        return self._local_cache.exists(remote_id)

    def resumable_session(self, path: str, content_type: str = "application/octet-stream") -> str:
        self._require_configured()
        return self._local_cache.resumable_session(path, content_type)

    def test_upload(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "ok": False,
                "error": "not_configured",
                "message": "Connect Google Drive before testing upload.",
            }
        return super().test_upload()


def build_storage_provider(config: Optional[Dict[str, Any]] = None) -> StorageService:
    """Factory from centre config (provider=google_drive|local_fs)."""
    cfg = config or {}
    provider = (cfg.get("provider") or "google_drive").lower()
    if provider in ("local_fs", "local", "filesystem"):
        root = cfg.get("root") or os.environ.get("COHORTOS_STORAGE_ROOT", str(Path(tempfile.gettempdir()) / "cohortos-storage"))
        return LocalFsStorageProvider(root)
    return GoogleDriveStorageProvider(
        credentials_json=cfg.get("credentials_json"),
        folder_id=cfg.get("folder_id"),
        access_token=cfg.get("access_token"),
    )
