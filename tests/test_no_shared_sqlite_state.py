"""Static guard: no long-lived sqlite connections outside the factory (P43)."""
from __future__ import annotations
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
FACTORY = ROOT / "models" / "base.py"
ALLOW_CONNECT = {
    str(FACTORY),
    str(ROOT / "services" / "sqlite_util.py"),
    str(ROOT / "scripts" / "migrate.py"),  # CLI migration tool
}

def _py_files():
    for base in ("models", "services", "api", "scripts", "tools"):
        d = ROOT / base
        if not d.is_dir():
            continue
        for p in d.rglob("*.py"):
            yield p

def test_sqlite_connect_only_in_factory():
    bad = []
    for p in _py_files():
        if str(p) in ALLOW_CONNECT:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if "sqlite3.connect(" in text:
            bad.append(str(p.relative_to(ROOT)))
    assert not bad, "sqlite3.connect outside factory:\n" + "\n".join(bad)

def test_no_self_conn_attribute_assignment_in_dal():
    text = (ROOT / "models" / "base.py").read_text()
    # Forbid assigning connection to self._conn
    assert not re.search(r"self\._conn\s*=", text), "self._conn assignment found"

def test_guard_negative_control_detects_bad_snippet():
    snippet = "class X:\n    def __init__(self):\n        self._conn = sqlite3.connect('x.db')\n"
    assert re.search(r"self\._conn\s*=", snippet)
    assert "sqlite3.connect(" in snippet
