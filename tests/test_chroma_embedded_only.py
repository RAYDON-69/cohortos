"""Chroma is embedded PersistentClient only — no server / HttpClient (CVE-2026-45829)."""
from pathlib import Path
import ast
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_no_chroma_http_client_in_source():
    offenders = []
    for path in (ROOT / "services").rglob("*.py"):
        text = path.read_text(errors="ignore")
        if "HttpClient" in text or "AsyncHttpClient" in text:
            offenders.append(str(path.relative_to(ROOT)))
        if "chroma run" in text or "CHROMA_SERVER" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"Chroma server/HTTP client usage: {offenders}"


def test_rag_uses_persistent_client():
    text = (ROOT / "services" / "rag_service.py").read_text()
    assert "PersistentClient" in text
    assert "HttpClient" not in text


def test_trust_remote_code_never_set():
    for path in (ROOT / "services").rglob("*.py"):
        text = path.read_text(errors="ignore")
        assert "trust_remote_code" not in text, path


def test_allowlist_expiry_logic():
    from datetime import date
    from scripts.pip_audit_gate import load_allow
    allow = load_allow("docs/PIP_AUDIT_ALLOWLIST.txt")
    assert "PYSEC-2026-311" in allow
    # Simulated expired entry must not pass
    expired = {"PYSEC-2026-311": {"reason": "x", "expires": "2020-01-01"}}
    assert expired["PYSEC-2026-311"]["expires"] < date.today().isoformat()
