"""B3: parallel writers on SQLite — WAL + busy_timeout, no user-facing lock errors."""
from __future__ import annotations
import sqlite3
import threading
import tempfile
from pathlib import Path
import pytest

LOCK_WAITS = {"n": 0}

def _connect(path):
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    def _busy(n):
        LOCK_WAITS["n"] += 1
        return n < 20
    try:
        conn.set_progress_handler(None, 0)
    except Exception:
        pass
    # sqlite3 busy handler
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

def test_50_parallel_writers_no_lost_updates():
    LOCK_WAITS["n"] = 0
    td = tempfile.mkdtemp()
    path = str(Path(td) / "c.db")
    conn = _connect(path)
    conn.execute("CREATE TABLE counters (id INTEGER PRIMARY KEY, n INTEGER NOT NULL)")
    conn.execute("INSERT INTO counters VALUES (1, 0)")
    conn.commit()
    conn.close()
    errors = []
    def worker(k):
        try:
            c = _connect(path)
            for _ in range(20):
                c.execute("BEGIN IMMEDIATE")
                cur = c.execute("SELECT n FROM counters WHERE id=1")
                n = cur.fetchone()[0]
                c.execute("UPDATE counters SET n=? WHERE id=1", (n + 1,))
                c.commit()
            c.close()
        except Exception as e:
            errors.append(str(e))
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads: t.start()
    for t in threads: t.join()
    # No "database is locked" should surface if busy_timeout works; some environments still race
    locked = [e for e in errors if "locked" in e.lower()]
    c = _connect(path)
    final = c.execute("SELECT n FROM counters WHERE id=1").fetchone()[0]
    c.close()
    assert final == 50 * 20, f"lost updates: final={final} errors={errors[:5]}"
    assert not locked, f"user-facing lock errors: {locked[:3]}"
