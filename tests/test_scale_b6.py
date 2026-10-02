"""B6 scale budgets (P38) — sized for CI minutes, not full 200k if too slow."""
from __future__ import annotations
import os
import time
import tempfile
from pathlib import Path
import pytest

@pytest.mark.timeout(120)
def test_scale_insert_and_query_budget():
    pytest.importorskip("psutil")
    import psutil
    import sqlite3
    td = tempfile.mkdtemp()
    db = str(Path(td) / "scale.db")
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("CREATE TABLE students (id TEXT PRIMARY KEY, tenant TEXT, name TEXT)")
    conn.execute("CREATE TABLE attendance (id INTEGER PRIMARY KEY, student_id TEXT, day TEXT)")
    conn.execute("CREATE TABLE fees (id INTEGER PRIMARY KEY, student_id TEXT, amount REAL)")
    n_students = int(os.environ.get("SCALE_STUDENTS", "5000"))
    t0 = time.perf_counter()
    conn.executemany(
        "INSERT INTO students VALUES (?,?,?)",
        [(f"s{i}", "t1", f"Student {i}") for i in range(n_students)],
    )
    conn.commit()
    insert_ms = (time.perf_counter() - t0) * 1000
    # attendance sample 200k is heavy; use 20k default for CI, override in full job
    n_att = int(os.environ.get("SCALE_ATTENDANCE", "20000"))
    t1 = time.perf_counter()
    conn.executemany(
        "INSERT INTO attendance(student_id, day) VALUES (?,?)",
        [(f"s{i % n_students}", f"2026-01-{(i % 28)+1:02d}") for i in range(n_att)],
    )
    conn.commit()
    att_ms = (time.perf_counter() - t1) * 1000
    t2 = time.perf_counter()
    n = conn.execute("SELECT COUNT(*) FROM attendance WHERE student_id='s1'").fetchone()[0]
    q_ms = (time.perf_counter() - t2) * 1000
    rss = psutil.Process().memory_info().rss / (1024 * 1024)
    print({"insert_students_ms": insert_ms, "insert_att_ms": att_ms, "query_ms": q_ms, "rss_mb": rss, "att_rows": n_att})
    assert insert_ms < 30000, f"student insert p95-ish {insert_ms}"
    assert q_ms < 500, f"query {q_ms}"
    assert rss < 3500, f"RSS {rss} MB exceeds 4GB profile headroom"
    conn.close()
