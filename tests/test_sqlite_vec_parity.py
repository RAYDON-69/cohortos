"""Parity: sqlite-vec default vs memory on fixed corpus (A3)."""
from services.vectorstores import get_vector_store, DEFAULT_BACKEND
from services.vectorstores.memory_store import MemoryVectorStore

CORPUS = [
    ("d1", "Batch A monthly fee is 1500 BDT for class 9"),
    ("d2", "Attendance marked present for student Rahim on Monday"),
    ("d3", "Exam syllabus covers algebra and geometry chapter 4"),
    ("d4", "Vault document: parent meeting notice in Bangla"),
    ("d5", "Refund policy: partial fee refund within 7 days"),
]

def _fill(vs):
    vs.add([c[0] for c in CORPUS], [c[1] for c in CORPUS], [{"i": i} for i in range(len(CORPUS))])

def test_default_backend_is_sqlite_vec():
    assert DEFAULT_BACKEND == "sqlite-vec"
    vs = get_vector_store()
    assert vs.__class__.__name__ == "SqliteVecStore"

def test_topk_overlap_with_memory(tmp_path):
    mem = MemoryVectorStore(tenant_id="parity")
    sql = get_vector_store("sqlite-vec", tenant_id="parity", db_path=str(tmp_path / "v.sqlite"))
    _fill(mem); _fill(sql)
    q = "monthly fee payment BDT"
    m_ids = [h["id"] for h in mem.query(q, n=3)]
    s_ids = [h["id"] for h in sql.query(q, n=3)]
    overlap = len(set(m_ids) & set(s_ids))
    assert overlap >= 2, f"top-k overlap {overlap} < 2: mem={m_ids} sql={s_ids}"
    # recall floor: d1 must be in top-3 for fee query
    assert "d1" in s_ids

def test_rss_hint_reasonable(tmp_path):
    sql = get_vector_store("sqlite-vec", tenant_id="rss", db_path=str(tmp_path / "r.sqlite"))
    _fill(sql)
    # tiny corpus << 4GB
    assert sql.rss_hint_mb() < 50
