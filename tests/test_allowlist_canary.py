from __future__ import annotations
from datetime import date
from pathlib import Path
ALLOW = Path(__file__).resolve().parents[1] / "docs" / "PIP_AUDIT_ALLOWLIST.txt"

def _days_left(marker="PYSEC-2026-311"):
    if not ALLOW.exists(): return None
    for ln in ALLOW.read_text().splitlines():
        if marker in ln and "|" in ln:
            exp = ln.split("|")[-1].strip()
            try:
                y,m,d = map(int, exp.split("-"))
                return (date(y,m,d) - date.today()).days
            except Exception: return None
    return None

def test_chromadb_allowlist_canary():
    days = _days_left()
    assert days is not None
    assert days > 7, f"Chroma allowlist expires in {days} days"
