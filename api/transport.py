"""Sync transport adapters for SyncEngine.transport."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.sync_remote import CloudSyncStore


class InProcessTransport:
    """Direct in-process client against a CloudSyncStore (tests / same process)."""

    def __init__(self, store: CloudSyncStore):
        self.store = store

    def push(
        self,
        tenant_id: str,
        operations: List[Dict[str, Any]],
        device_id: str = "",
    ) -> Dict[str, Any]:
        return self.store.push(tenant_id, operations, device_id=device_id)

    def pull(
        self,
        tenant_id: str,
        since_seq: int = 0,
        limit: int = 200,
        exclude_device: str = "",
    ) -> Dict[str, Any]:
        return self.store.pull(
            tenant_id, since_seq=since_seq, limit=limit, exclude_device=exclude_device
        )


class HttpSyncTransport:
    """HTTP client against /sync/push and /sync/pull."""

    def __init__(self, base_url: str, access_token: str, httpx_client=None):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self._client = httpx_client

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def push(self, tenant_id: str, operations, device_id: str = ""):
        import httpx
        client = self._client or httpx.Client()
        r = client.post(
            f"{self.base_url}/sync/push",
            json={"operations": operations, "device_id": device_id},
            headers=self._headers(),
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def pull(self, tenant_id: str, since_seq: int = 0, limit: int = 200, exclude_device: str = ""):
        import httpx
        client = self._client or httpx.Client()
        r = client.post(
            f"{self.base_url}/sync/pull",
            json={"since_seq": since_seq, "limit": limit, "device_id": exclude_device},
            headers=self._headers(),
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
