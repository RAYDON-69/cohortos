from services.vectorstores import get_vector_store

def test_memory_store_retrieval_parity():
    vs = get_vector_store("memory", tenant_id="t1")
    vs.add(
        ["d1", "d2", "d3"],
        ["Batch A fee is 1500 BDT monthly", "Attendance was marked present for Rahim", "Exam syllabus covers algebra"],
        [{"type": "fee"}, {"type": "attendance"}, {"type": "exam"}],
    )
    hits = vs.query("fee monthly payment", n=2)
    assert hits[0]["id"] == "d1"
    assert vs.count() == 3

def test_sqlite_vec_alias_backend():
    vs = get_vector_store("sqlite-vec", tenant_id="t2")
    vs.add(["x"], ["hello world"])
    assert vs.query("hello")[0]["id"] == "x"
