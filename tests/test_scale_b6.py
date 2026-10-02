"""B6 scale budgets (P39) — 5k students, 200k attendance, 20k fees under RSS cap."""
from __future__ import annotations
import os
import time
import tempfile
from pathlib import Path
import pytest

@pytest.mark.timeout(300)
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
    n_att = int(os.environ.get("SCALE_ATTENDANCE", "200000"))
    n_fees = int(os.environ.get("SCALE_FEES", "20000"))
    t0 = time.perf_counter()
    conn.executemany(
        "INSERT INTO students VALUES (?,?,?)",
        [(f"s{i}", "t1", f"Student {i}") for i in range(n_students)],
    )
    conn.commit()
    insert_ms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    batch = 5000
    for start in range(0, n_att, batch):
        chunk = [
            (f"s{i % n_students}", f"2026-{(i % 12)+1:02d}-{(i % 28)+1:02d}")
            for i in range(start, min(start + batch, n_att))
        ]
        conn.executemany("INSERT INTO attendance(student_id, day) VALUES (?,?)", chunk)
        conn.commit()
    att_ms = (time.perf_counter() - t1) * 1000
    t_f = time.perf_counter()
    conn.executemany(
        "INSERT INTO fees(student_id, amount) VALUES (?,?)",
        [(f"s{i % n_students}", float(i % 500)) for i in range(n_fees)],
    )
    conn.commit()
    fees_ms = (time.perf_counter() - t_f) * 1000
    t2 = time.perf_counter()
    n = conn.execute("SELECT COUNT(*) FROM attendance WHERE student_id='s1'").fetchone()[0]
    q_ms = (time.perf_counter() - t2) * 1000
    rss = psutil.Process().memory_info().rss / (1024 * 1024)
    print({
        "students": n_students, "attendance": n_att, "fees": n_fees,
        "insert_students_ms": insert_ms, "insert_att_ms": att_ms, "insert_fees_ms": fees_ms,
        "query_ms": q_ms, "rss_mb": rss, "s1_att_rows": n,
    })
    assert insert_ms < 60000, f"student insert {insert_ms}"
    assert q_ms < 2000, f"query {q_ms}"
    assert rss < 3500, f"RSS {rss} MB exceeds 4GB profile headroom"
    assert conn.execute("SELECT COUNT(*) FROM fees").fetchone()[0] == n_fees
    conn.close()
