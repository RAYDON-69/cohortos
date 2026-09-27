"""
Local GGUF inference for offline Copilot (Phase 22).

Packaging decision: download-on-first-run (not bundled in the installer).
  - LFM2.5-1.2B / Qwen2.5-1.5B GGUF is ~0.8–1.5GB; bundling blows past
    GitHub Actions artifact quotas and desktop release payloads.
  - First use downloads from Hugging Face into COHORTOS_LOCAL_MODEL_DIR
    with a progress file for UI; subsequent runs load from disk.
  - Model id is config-driven (Settings → AI keys / env) so Qwen2.5-1.5B-Instruct-FC
    swaps in without a code change.

Default model id: lfm2.5-1.2b-instruct (LFM2.5-1.2B-Instruct GGUF).
Alternate: qwen2.5-1.5b-instruct-fc.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Registry: logical id → (hf_repo_or_url, filename, display_name)
# URLs point at Hugging Face resolve endpoints; override via COHORTOS_LOCAL_MODEL_URL.
MODEL_REGISTRY: Dict[str, Dict[str, str]] = {
    "lfm2.5-1.2b-instruct": {
        "filename": "LFM2.5-1.2B-Instruct-Q4_K_M.gguf",
        # Community / LiquidAI-style GGUF; override with COHORTOS_LOCAL_MODEL_URL if mirror moves
        "url": os.environ.get(
            "COHORTOS_LOCAL_MODEL_URL_LFM",
            "https://huggingface.co/bartowski/LFM2-1.2B-Instruct-GGUF/resolve/main/LFM2-1.2B-Instruct-Q4_K_M.gguf",
        ),
        "display": "LFM2.5-1.2B-Instruct (local GGUF)",
    },
    "qwen2.5-1.5b-instruct-fc": {
        "filename": "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
        "url": os.environ.get(
            "COHORTOS_LOCAL_MODEL_URL_QWEN",
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        ),
        "display": "Qwen2.5-1.5B-Instruct-FC (local GGUF)",
    },
}

_lock = threading.Lock()
_llm_cache: Dict[str, Any] = {}
_progress: Dict[str, Any] = {"status": "idle", "pct": 0, "model_id": None, "error": None}


def model_dir() -> Path:
    d = Path(os.environ.get("COHORTOS_LOCAL_MODEL_DIR") or "/tmp/cohortos-models")
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_model_id(cfg: Optional[Dict[str, Any]] = None) -> str:
    cfg = cfg or {}
    mid = (
        str(cfg.get("local_model_id") or "").strip()
        or os.environ.get("COHORTOS_LOCAL_MODEL_ID")
        or "lfm2.5-1.2b-instruct"
    )
    return mid if mid in MODEL_REGISTRY else "lfm2.5-1.2b-instruct"


def progress() -> Dict[str, Any]:
    return dict(_progress)


def model_path(model_id: Optional[str] = None) -> Path:
    mid = model_id or resolve_model_id()
    meta = MODEL_REGISTRY.get(mid) or MODEL_REGISTRY["lfm2.5-1.2b-instruct"]
    return model_dir() / meta["filename"]


def ensure_model(model_id: Optional[str] = None, force: bool = False) -> Path:
    """Download GGUF on first run if missing. Returns local path."""
    mid = model_id or resolve_model_id()
    meta = MODEL_REGISTRY.get(mid) or MODEL_REGISTRY["lfm2.5-1.2b-instruct"]
    path = model_dir() / meta["filename"]
    if path.is_file() and path.stat().st_size > 10_000_000 and not force:
        return path
    # Allow fully offline tests: if COHORTOS_SKIP_MODEL_DOWNLOAD=1, raise soft error
    if os.environ.get("COHORTOS_SKIP_MODEL_DOWNLOAD") == "1":
        raise FileNotFoundError(
            f"Local model {mid} not present and COHORTOS_SKIP_MODEL_DOWNLOAD=1"
        )
    url = os.environ.get("COHORTOS_LOCAL_MODEL_URL") or meta["url"]
    _progress.update({"status": "downloading", "pct": 0, "model_id": mid, "error": None})
    tmp = path.with_suffix(path.suffix + ".part")

    def _report(blocknum: int, blocksize: int, totalsize: int) -> None:
        if totalsize > 0:
            pct = min(99, int(blocknum * blocksize * 100 / totalsize))
            _progress["pct"] = pct

    try:
        urllib.request.urlretrieve(url, str(tmp), reporthook=_report)
        tmp.replace(path)
        _progress.update({"status": "ready", "pct": 100, "model_id": mid})
        return path
    except Exception as e:
        _progress.update({"status": "error", "error": str(e), "model_id": mid})
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass
        raise


def get_llama(model_id: Optional[str] = None, n_ctx: int = 4096):
    """Load llama-cpp Llama instance (cached). Requires llama-cpp-python."""
    mid = model_id or resolve_model_id()
    with _lock:
        if mid in _llm_cache:
            return _llm_cache[mid]
        try:
            from llama_cpp import Llama  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "llama-cpp-python is not installed. pip install llama-cpp-python"
            ) from e
        path = ensure_model(mid)
        n_threads = int(os.environ.get("COHORTOS_LOCAL_N_THREADS") or max(2, (os.cpu_count() or 4) // 2))
        n_gpu = int(os.environ.get("COHORTOS_LOCAL_N_GPU_LAYERS") or "0")
        llm = Llama(
            model_path=str(path),
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_gpu_layers=n_gpu,
            verbose=False,
        )
        _llm_cache[mid] = llm
        _progress.update({"status": "ready", "pct": 100, "model_id": mid})
        return llm


def local_complete(
    prompt: str,
    *,
    model_id: Optional[str] = None,
    system: str = "",
    max_tokens: int = 512,
    temperature: float = 0.2,
) -> str:
    """Chat-complete with local GGUF. Returns assistant text."""
    llm = get_llama(model_id)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    out = llm.create_chat_completion(
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    choice = (out.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return str(msg.get("content") or "").strip()


def local_available() -> bool:
    try:
        import llama_cpp  # noqa: F401
        return True
    except Exception:
        return False
