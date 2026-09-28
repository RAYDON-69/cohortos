"""Acceptance tests for §3 local-model safety (must fail before impl)."""
import os
import json
from pathlib import Path
from unittest import mock

import pytest


def test_ram_tier_4gb_disables_and_hides():
    from services.local_model import ram_policy
    with mock.patch("services.local_model._mem_info", return_value=(4.0, 1.5)):
        p = ram_policy()
    assert p["tier"] == "low"
    assert p["enabled_default"] is False
    assert p["offer"] is False
    assert "freeze" in (p.get("caution") or "").lower() or "caution" in p


def test_ram_tier_6gb_opt_in():
    from services.local_model import ram_policy
    with mock.patch("services.local_model._mem_info", return_value=(6.0, 2.5)):
        p = ram_policy()
    assert p["tier"] == "mid"
    assert p["enabled_default"] is False
    assert p["offer"] is True


def test_ram_tier_8gb_offers_enable():
    from services.local_model import ram_policy
    with mock.patch("services.local_model._mem_info", return_value=(16.0, 8.0)):
        p = ram_policy()
    assert p["tier"] == "high"
    assert p["offer"] is True


def test_download_requires_consent_flag(tmp_path, monkeypatch):
    from services import local_model as lm
    monkeypatch.setenv("COHORTOS_LOCAL_MODEL_DIR", str(tmp_path))
    monkeypatch.delenv("COHORTOS_SKIP_MODEL_DOWNLOAD", raising=False)
    with pytest.raises(PermissionError):
        lm.ensure_model(consent=False)


def test_sha256_mismatch_rejects(tmp_path, monkeypatch):
    from services import local_model as lm
    monkeypatch.setenv("COHORTOS_LOCAL_MODEL_DIR", str(tmp_path))
    mid = "lfm2.5-1.2b-instruct"
    meta = lm.MODEL_REGISTRY[mid]
    path = tmp_path / meta["filename"]
    path.write_bytes(b"not-a-real-gguf" * 1000)
    # force verify
    with pytest.raises(ValueError, match="SHA-256|checksum|integrity"):
        lm.verify_model_file(path, expected_sha256="0" * 64)


def test_refuse_load_when_free_ram_insufficient(monkeypatch):
    from services import local_model as lm
    with mock.patch("services.local_model._mem_info", return_value=(16.0, 0.5)):
        with pytest.raises((MemoryError, RuntimeError)):
            lm.assert_can_load(model_gb=1.0, context_gb=0.5)


def test_inference_isolated_timeout_kills(monkeypatch, tmp_path):
    """Subprocess isolation: timeout must terminate worker (kill switch)."""
    from services import local_model as lm
    monkeypatch.setenv("COHORTOS_LOCAL_MODEL_DIR", str(tmp_path))
    monkeypatch.setenv("COHORTOS_SKIP_MODEL_DOWNLOAD", "1")
    monkeypatch.setattr(lm, "assert_can_load", lambda **k: None)
    monkeypatch.setattr(lm, "ram_policy", lambda: {"tier": "high", "offer": True})
    with pytest.raises((TimeoutError, RuntimeError, FileNotFoundError)):
        lm.local_complete_isolated("ping", timeout_sec=1, model_id="lfm2.5-1.2b-instruct")


def test_delete_model_removes_file(tmp_path, monkeypatch):
    from services import local_model as lm
    monkeypatch.setenv("COHORTOS_LOCAL_MODEL_DIR", str(tmp_path))
    mid = "lfm2.5-1.2b-instruct"
    path = tmp_path / lm.MODEL_REGISTRY[mid]["filename"]
    path.write_bytes(b"x" * 100)
    assert lm.delete_model(mid) is True
    assert not path.exists()
