"""
Base model for CohortOS with unified tenant context and offline-first support.

DataAccessLayer is SQLite-backed. Default db_path=':memory:' keeps tests
isolated. Pass a filesystem path for durable persistence across restarts.
Complex values (list/dict) are JSON-serialized transparently so service
signatures stay unchanged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, Union
from dataclasses import dataclass
import uuid
import json
import sqlite3
import threading
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _utcnow() -> str:
    """Timezone-aware UTC timestamp (ISO format)."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TenantContext:
    """Current tenant context for all operations"""
    tenant_id: uuid.UUID
    mode: str = 'offline-first'  # offline-first, cloud-first, hybrid

    def __post_init__(self):
        if isinstance(self.tenant_id, str):
            self.tenant_id = uuid.UUID(self.tenant_id)
        elif not isinstance(self.tenant_id, uuid.UUID):
            raise ValueError(f"tenant_id must be UUID or string UUID, got {type(self.tenant_id)}")
        if self.mode not in ['offline-first', 'cloud-first', 'hybrid']:
            raise ValueError(f"Invalid mode: {self.mode}")


class BaseModel(ABC):
    """Base class for all CohortOS models with tenant context"""

    def __init__(self, tenant_context: TenantContext):
        self.tenant_context = tenant_context

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary for storage"""
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any], tenant_context: TenantContext) -> 'BaseModel':
        """Create model from dictionary"""
        pass

    @abstractmethod
    def get_table_name(self) -> str:
        """Get the table name for this model"""
        pass

    @abstractmethod
    def get_primary_key(self) -> str:
        """Get the primary key field name"""
        pass


# ── SQLite helpers ────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS _records (
    table_name TEXT NOT NULL,
    id         TEXT NOT NULL,
    tenant_id  TEXT NOT NULL,
    data       TEXT NOT NULL,
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT,
    updated_at TEXT,
    PRIMARY KEY (table_name, id)
);
CREATE INDEX IF NOT EXISTS idx_records_tenant
    ON _records (table_name, tenant_id);
CREATE INDEX IF NOT EXISTS idx_records_active
    ON _records (table_name, tenant_id, is_active);
"""

# Per-thread connections (sqlite3 connections are not cross-thread safe).
# File DBs: key = path. Shared memory: key = URI file:cohortos_mem_<id>?mode=memory&cache=shared
# A sentinel connection per shared-memory URI keeps the DB alive until close_all().
_conn_lock = threading.Lock()
_thread_local = threading.local()
_all_conns: Dict[int, Dict[str, sqlite3.Connection]] = {}
_mem_sentinels: Dict[str, sqlite3.Connection] = {}
_schema_ready: set = set()  # keys that have had schema applied under lock


def _json_default(obj: Any) -> Any:
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _encode(data: Dict[str, Any]) -> str:
    return json.dumps(data, default=_json_default, ensure_ascii=False)


def _decode(raw: str) -> Dict[str, Any]:
    return json.loads(raw)


def _resolve_migrations_dir() -> Optional[Path]:
    """Locate migrations/ relative to this package or CWD."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "migrations",
        Path.cwd() / "migrations",
        Path(__file__).resolve().parents[1] / "migrations",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def apply_sqlite_migrations(conn: sqlite3.Connection, migrations_dir: Optional[Path] = None) -> int:
    """
    Apply migrations/003–012 idempotently on an open connection.
    Returns number of newly applied files.
    """
    migrations_dir = migrations_dir or _resolve_migrations_dir()
    files = [
        "003_sync_queue.sql",
        "004_notifications.sql",
        "005_admission.sql",
        "006_attendance.sql",
        "007_payments.sql",
        "008_exams.sql",
        "009_content.sql",
        "010_ai.sql",
        "011_accounts.sql",
        "012_saas.sql",
    ]
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    applied = {
        row[0]
        for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
    }
    count = 0
    if not migrations_dir:
        return 0
    for name in files:
        if name in applied:
            continue
        path = migrations_dir / name
        if not path.exists():
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (?)", (name,)
            )
            conn.commit()
            count += 1
        except sqlite3.Error:
            conn.rollback()
            # Non-fatal for domain document store; native tables best-effort
            continue
    return count




# ── Local rotating backups ────────────────────────────────────────────

BACKUP_KEEP = 7
BACKUP_EVERY_N_WRITES = 50


def backup_dir_for(db_path: str) -> Path:
    """Rotating backup folder sits next to the primary db file."""
    path = Path(db_path).resolve()
    return path.parent / f"{path.name}.backups"


def list_backups(db_path: str) -> List[Path]:
    """Newest first."""
    bdir = backup_dir_for(db_path)
    if not bdir.is_dir():
        return []
    files = sorted(bdir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def create_backup(db_path: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Path]:
    """
    Copy primary .db into the rotating backup folder. Keeps last BACKUP_KEEP.
    Returns path of the new backup, or None if skipped (memory db / missing file).
    """
    if not db_path or db_path == ":memory:":
        return None
    src = Path(db_path)
    if not src.is_file():
        return None

    if conn is not None:
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        except sqlite3.Error:
            try:
                conn.commit()
            except sqlite3.Error:
                pass

    bdir = backup_dir_for(db_path)
    bdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    dest = bdir / f"{src.stem}_{stamp}.db"
    shutil.copy2(str(src), str(dest))

    # Rotate: keep newest BACKUP_KEEP
    existing = list_backups(db_path)
    for old in existing[BACKUP_KEEP:]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


def restore_from_backup(
    db_path: str,
    backup_path: Optional[str] = None,
) -> Path:
    """
    Replace primary db with a backup. If backup_path is None, use the newest.
    Closes any cached connections to the primary first.
    Returns the path of the backup that was restored.
    """
    if not db_path or db_path == ":memory:":
        raise ValueError("Cannot restore into :memory: database")

    DataAccessLayer.close_all()

    if backup_path:
        src = Path(backup_path)
    else:
        backups = list_backups(db_path)
        if not backups:
            raise FileNotFoundError(f"No backups found for {db_path}")
        src = backups[0]

    if not src.is_file():
        raise FileNotFoundError(f"Backup not found: {src}")

    dest = Path(db_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Safety copy of corrupted primary if it exists
    if dest.is_file():
        broken = dest.with_suffix(dest.suffix + ".corrupted")
        try:
            shutil.copy2(str(dest), str(broken))
        except OSError:
            pass
    # Drop WAL/SHM sidecars so a restored file is not overwritten by stale journal
    for side in (str(dest) + "-wal", str(dest) + "-shm", str(dest) + "-journal"):
        try:
            Path(side).unlink(missing_ok=True)
        except OSError:
            pass
    shutil.copy2(str(src), str(dest))
    # Ensure no sidecar left from the backup source either
    for side in (str(dest) + "-wal", str(dest) + "-shm"):
        try:
            Path(side).unlink(missing_ok=True)
        except OSError:
            pass
    return src


class DataAccessLayer:
    """
    Unified data access layer — SQLite-backed, offline-first.

    Parameters
    ----------
    tenant_context : TenantContext
    db_path : str | None
        ':memory:' (default) → isolated in-memory DB per instance (tests).
        Filesystem path → durable SQLite file; survives process restart.
        Multiple instances with the same file path share one connection.
    auto_migrate : bool
        When True (default) and db_path is a real file, run migrations 003–012.
    """

    def __init__(
        self,
        tenant_context: TenantContext,
        db_path: Optional[str] = None,
        auto_migrate: bool = True,
    ):
        self.tenant_context = tenant_context
        self.db_path = db_path if db_path is not None else ":memory:"
        if self.db_path == ":memory:" or self.db_path.startswith(":memory:"):
            # Shared-cache URI keyed by path label so all threads/DAL instances
            # with the same db_path share data (fixes OTP/account under TestClient threads).
            # Tests needing isolation should pass a tempfile path, not :memory:.
            label = "default" if self.db_path == ":memory:" else self.db_path.replace(":", "_")
            self._conn_key = f"file:cohortos_mem_{label}?mode=memory&cache=shared"
            self._is_shared_memory = True
        elif self.db_path.startswith("file:") and "mode=memory" in self.db_path:
            self._conn_key = self.db_path
            self._is_shared_memory = True
        else:
            self._conn_key = self.db_path
            self._is_shared_memory = False
        self.pending_operations: List[Dict[str, Any]] = []
        self._closed = False

        # Backward-compat attribute some older tests may inspect
        self.local_storage: Dict[str, list] = {}

        # Open calling-thread connection and ensure schema (no long-lived self.conn)
        c = self.conn
        c.execute("PRAGMA foreign_keys = ON")
        c.executescript(_SCHEMA_SQL)
        c.commit()

        if auto_migrate and not getattr(self, "_is_shared_memory", False) and self.db_path not in (":memory:",):
            apply_sqlite_migrations(c)

        # Rotating local backups (file-backed only)
        self._write_count = 0
        self._backup_every = BACKUP_EVERY_N_WRITES
        if self.db_path not in (":memory:",) and Path(self.db_path).is_file():
            try:
                create_backup(self.db_path, conn=c)
            except Exception:
                pass  # backup must never block startup

    # ── connection management ─────────────────────────────────────────

    @property
    def conn(self) -> sqlite3.Connection:
        """Always the calling thread's connection for this db key."""
        if self._closed and self.db_path == ":memory:":
            raise RuntimeError("DAL closed")
        return self._open_connection(getattr(self, "_conn_key", self.db_path))



    @staticmethod
    def _open_connection(db_path: str) -> sqlite3.Connection:
        """Return calling-thread connection for file path or shared-memory URI."""
        tid = threading.get_ident()
        store = getattr(_thread_local, "conns", None)
        if store is None:
            store = {}
            _thread_local.conns = store
        if db_path in store:
            return store[db_path]
        with _conn_lock:
            if db_path in store:
                return store[db_path]
            is_mem = db_path.startswith("file:") and "mode=memory" in db_path
            is_legacy_mem = db_path == ":memory:" or db_path.startswith(":memory:")
            if is_mem:
                # Keep a process-wide sentinel so shared memory DB is not dropped
                if db_path not in _mem_sentinels:
                    sent = sqlite3.connect(db_path, uri=True, timeout=30.0, check_same_thread=False)
                    sent.row_factory = sqlite3.Row
                    try:
                        sent.execute("PRAGMA foreign_keys=ON")
                    except Exception:
                        pass
                    _mem_sentinels[db_path] = sent
                conn = sqlite3.connect(db_path, uri=True, timeout=30.0, check_same_thread=True)
                conn.row_factory = sqlite3.Row
                try:
                    conn.execute("PRAGMA foreign_keys=ON")
                except Exception:
                    pass
            elif is_legacy_mem:
                # Should not happen after __init__ rewrite; private memory fallback
                conn = sqlite3.connect(":memory:", check_same_thread=True)
                conn.row_factory = sqlite3.Row
            else:
                parent = Path(db_path).parent
                if str(parent) not in ("", "."):
                    parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=True)
                conn.row_factory = sqlite3.Row
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA busy_timeout=30000")
                    conn.execute("PRAGMA foreign_keys=ON")
                    conn.execute("PRAGMA synchronous=NORMAL")
                except Exception:
                    pass
            # Schema once per key under lock
            if db_path not in _schema_ready:
                try:
                    conn.executescript(_SCHEMA_SQL)
                    conn.commit()
                    if not is_mem and not is_legacy_mem:
                        apply_sqlite_migrations(conn)
                    _schema_ready.add(db_path)
                except Exception:
                    try:
                        conn.executescript(_SCHEMA_SQL)
                        conn.commit()
                        _schema_ready.add(db_path)
                    except Exception:
                        pass
            else:
                # Still ensure IF NOT EXISTS on this connection (cheap)
                try:
                    conn.executescript(_SCHEMA_SQL)
                    conn.commit()
                except Exception:
                    pass
            store[db_path] = conn
            _all_conns.setdefault(tid, {})[db_path] = conn
            return conn

    def close(self) -> None:
        """Close this layer. File-backed connections stay until close_all();
        :memory: connections are closed here."""
        if self._closed:
            return
        if self.db_path == ":memory:":
            try:
                # Open without going through closed-guard
                c = self._open_connection(self.db_path)
                c.close()
            except Exception:
                pass
        self._closed = True
        # File-backed: leave in per-thread cache so other instances keep working

    @classmethod
    def close_all(cls) -> None:
        """Close every per-thread connection and shared-memory sentinels."""
        with _conn_lock:
            for tid, store in list(_all_conns.items()):
                if not isinstance(store, dict):
                    try:
                        store.close()
                    except Exception:
                        pass
                    continue
                for path, conn in list(store.items()):
                    try:
                        conn.close()
                    except Exception:
                        pass
            _all_conns.clear()
            for uri, sent in list(_mem_sentinels.items()):
                try:
                    sent.close()
                except Exception:
                    pass
            _mem_sentinels.clear()
            _schema_ready.clear()
            try:
                _thread_local.conns = {}
            except Exception:
                pass

    def ensure_migrated(self) -> int:
        """Re-run migration check (idempotent). Returns newly applied count."""
        return apply_sqlite_migrations(self.conn)

    # ── tenant helpers ────────────────────────────────────────────────

    def get_tenant_id(self) -> uuid.UUID:
        return self.tenant_context.tenant_id

    def get_mode(self) -> str:
        return self.tenant_context.mode

    # ── backup trigger ────────────────────────────────────────────────

    def _note_write(self) -> None:
        """Count writes; every N file-backed writes, take a rotating backup."""
        if self.db_path in (":memory:",):
            return
        self._write_count += 1
        if self._write_count % self._backup_every == 0:
            try:
                create_backup(self.db_path, conn=self.conn)
            except Exception:
                pass

    def backup_now(self) -> Optional[Path]:
        """Force an immediate backup (file-backed only)."""
        if self.db_path in (":memory:",):
            return None
        return create_backup(self.db_path, conn=self.conn)

    # ── CRUD (same signatures as in-memory version) ───────────────────

    def create(self, table_name: str, data: Dict[str, Any]) -> uuid.UUID:
        """Create a new record, works with zero network."""
        record_id = uuid.uuid4()
        payload = dict(data)
        payload["id"] = str(record_id)
        payload["tenant_id"] = str(self.get_tenant_id())
        payload.setdefault("created_at", _utcnow())
        payload["updated_at"] = _utcnow()
        if "is_active" not in payload:
            payload["is_active"] = True

        self.conn.execute(
            """
            INSERT OR REPLACE INTO _records
                (table_name, id, tenant_id, data, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                table_name,
                str(record_id),
                str(self.get_tenant_id()),
                _encode(payload),
                1 if payload.get("is_active", True) else 0,
                payload.get("created_at"),
                payload.get("updated_at"),
            ),
        )
        self.conn.commit()
        self._note_write()

        if self.get_mode() in ["offline-first", "hybrid"]:
            self.pending_operations.append({
                "operation": "create",
                "table": table_name,
                "data": payload,
                "record_id": record_id,
            })

        return record_id

    def get(self, table_name: str, record_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get a single record for the current tenant."""
        row = self.conn.execute(
            """
            SELECT data FROM _records
            WHERE table_name = ? AND id = ? AND tenant_id = ?
            """,
            (table_name, str(record_id), str(self.get_tenant_id())),
        ).fetchone()
        if not row:
            return None
        return _decode(row[0])

    def get_all(self, table_name: str) -> List[Dict[str, Any]]:
        """Get all records for the current tenant."""
        rows = self.conn.execute(
            """
            SELECT data FROM _records
            WHERE table_name = ? AND tenant_id = ?
            """,
            (table_name, str(self.get_tenant_id())),
        ).fetchall()
        return [_decode(r[0]) for r in rows]

    def update(self, table_name: str, record_id: uuid.UUID, data: Dict[str, Any]) -> bool:
        """Update a record for the current tenant."""
        existing = self.get(table_name, record_id)
        if existing is None:
            return False

        old_state = dict(existing)
        existing.update(data)
        existing["updated_at"] = _utcnow()
        is_active = existing.get("is_active", True)
        if isinstance(is_active, bool):
            active_int = 1 if is_active else 0
        else:
            active_int = 1 if is_active not in (0, "0", False, "false", None) else 0

        self.conn.execute(
            """
            UPDATE _records
            SET data = ?, is_active = ?, updated_at = ?
            WHERE table_name = ? AND id = ? AND tenant_id = ?
            """,
            (
                _encode(existing),
                active_int,
                existing["updated_at"],
                table_name,
                str(record_id),
                str(self.get_tenant_id()),
            ),
        )
        self.conn.commit()
        self._note_write()

        if self.get_mode() in ["offline-first", "hybrid"]:
            self.pending_operations.append({
                "operation": "update",
                "table": table_name,
                "old_state": old_state,
                "new_state": dict(existing),
                "record_id": record_id,
            })
        return True

    def delete(self, table_name: str, record_id: uuid.UUID) -> bool:
        """Soft-delete a record (is_active=False)."""
        existing = self.get(table_name, record_id)
        if existing is None:
            return False

        old_state = dict(existing)
        existing["is_active"] = False
        existing["updated_at"] = _utcnow()

        self.conn.execute(
            """
            UPDATE _records
            SET data = ?, is_active = 0, updated_at = ?
            WHERE table_name = ? AND id = ? AND tenant_id = ?
            """,
            (
                _encode(existing),
                existing["updated_at"],
                table_name,
                str(record_id),
                str(self.get_tenant_id()),
            ),
        )
        self.conn.commit()
        self._note_write()

        if self.get_mode() in ["offline-first", "hybrid"]:
            self.pending_operations.append({
                "operation": "delete",
                "table": table_name,
                "old_state": old_state,
                "record_id": record_id,
            })
        return True

    def get_pending_operations(self) -> List[Dict[str, Any]]:
        return self.pending_operations.copy()

    def clear_pending_operations(self) -> None:
        self.pending_operations.clear()
