from pathlib import Path

def test_requirements_has_no_chromadb():
    text = Path("requirements.txt").read_text().lower()
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        assert "chromadb" not in s, line
        assert "vector-stores-chroma" not in s, line

def test_app_defaults_to_sqlite_vec():
    from services.vectorstores import DEFAULT_BACKEND, get_vector_store
    assert DEFAULT_BACKEND == "sqlite-vec"
    vs = get_vector_store()
    assert vs.__class__.__name__ == "SqliteVecStore"
