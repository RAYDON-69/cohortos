"""Shared SQLite open with WAL, busy_timeout, and lock-wait counter (P39)."""
from __future__ import annotations
import sqlite3
from typing import Any

LOCK_WAIT_COUNT = {"n": 0}

def get_lock_wait_count() -> int:
    return int(LOCK_WAIT_COUNT.get("n", 0))

def open_sqlite(path: str, **kwargs: Any) -> sqlite3.Connection:
    timeout = kwargs.pop("timeout", 30.0)
    check_same_thread = kwargs.pop("check_same_thread", False)
    conn = sqlite3.connect(path, timeout=timeout, check_same_thread=check_same_thread, **kwargs)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
    except Exception:
        pass
    def _busy(n: int) -> int:
        LOCK_WAIT_COUNT["n"] += 1
        return 1 if n < 50 else 0
    try:
        conn.set_progress_handler(None, 0)
        # busy handler API
        if hasattr(conn, "set_busy_handler"):
            conn.set_busy_handler(_busy)  # type: ignore
    except Exception:
        pass
    return conn
