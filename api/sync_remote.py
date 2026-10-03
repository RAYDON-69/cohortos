"""
Minimal cloud sync store — SQLite-backed, one server-side queue per tenant.

Reuses domain operation shape from models.sync.SyncOperation.
Does not introduce a new database engine.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class CloudSyncStore:
    """
    Server-side durable log of sync operations per tenant.
    Clients push local ops here and pull ops from other devices.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = threading.RLock()
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # Each :memory: connection is private; use shared cache URI for memory tests if needed
        from services.sqlite_util import open_sqlite
        self._conn = open_sqlite(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cloud_ops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    op_id TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL,
                    device_id TEXT NOT NULL DEFAULT '',
                    operation_type TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    old_state TEXT,
                    new_state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    server_seq INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_cloud_tenant_seq
                    ON cloud_ops (tenant_id, id);
                """
            )
            self._conn.commit()

    def push(
        self,
        tenant_id: str,
        operations: List[Dict[str, Any]],
        device_id: str = "",
    ) -> Dict[str, Any]:
        accepted = 0
        duplicates = 0
        with self._lock:
            for op in operations:
                op_id = op.get("op_id") or op.get("id") or str(uuid.uuid4())
                try:
                    self._conn.execute(
                        """
                        INSERT INTO cloud_ops
                        (op_id, tenant_id, device_id, operation_type, table_name,
                         record_id, old_state, new_state, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(op_id),
                            tenant_id,
                            device_id,
                            op.get("operation_type") or op.get("op") or "update",
                            op.get("table_name") or op.get("table") or "",
                            str(op.get("record_id") or ""),
                            json.dumps(op.get("old_state")) if op.get("old_state") is not None else None,
                            json.dumps(op.get("new_state") or op.get("data") or {}),
                            op.get("created_at") or _utcnow(),
                        ),
                    )
                    accepted += 1
                except sqlite3.IntegrityError:
                    duplicates += 1
            self._conn.commit()
        return {"accepted": accepted, "duplicates": duplicates}

    def pull(
        self,
        tenant_id: str,
        since_seq: int = 0,
        limit: int = 200,
        exclude_device: str = "",
    ) -> Dict[str, Any]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, op_id, device_id, operation_type, table_name, record_id,
                       old_state, new_state, created_at
                FROM cloud_ops
                WHERE tenant_id = ? AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (tenant_id, int(since_seq), int(limit)),
            ).fetchall()
        ops = []
        max_seq = since_seq
        for r in rows:
            if exclude_device and r["device_id"] == exclude_device:
                max_seq = max(max_seq, r["id"])
                continue
            ops.append(
                {
                    "seq": r["id"],
                    "op_id": r["op_id"],
                    "device_id": r["device_id"],
                    "operation_type": r["operation_type"],
                    "table_name": r["table_name"],
                    "record_id": r["record_id"],
                    "old_state": json.loads(r["old_state"]) if r["old_state"] else None,
                    "new_state": json.loads(r["new_state"]) if r["new_state"] else {},
                    "created_at": r["created_at"],
                }
            )
            max_seq = max(max_seq, r["id"])
        return {"operations": ops, "cursor": max_seq}

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
