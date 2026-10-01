"""
Local GGUF inference with §3 safety (Phase 23).

Inference isolation decision: **subprocess worker** (not a long-lived HTTP sidecar).
Evidence:
- Desk is single-user; concurrent model servers add port/lifecycle complexity.
- Kill switch = terminate PID on timeout; matches ROADMAP "timeout and kill switch".
- llama-cpp-python in-process would freeze the API event loop on 4GB machines.
- Sidecar (llama.cpp server) remains a future option if multi-window concurrency appears.

Packaging: download-on-first-run into COHORTOS_LOCAL_MODEL_DIR; optional dep
llama-cpp-python. CI sets COHORTOS_SKIP_MODEL_DOWNLOAD=1.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from services.safe_http import safe_urlopen

# Pinned revisions + SHA-256 (update when changing quant/revision)
MODEL_REGISTRY: Dict[str, Dict[str, str]] = {
    "lfm2.5-1.2b-instruct": {
        "filename": "LFM2-1.2B-Instruct-Q4_K_M.gguf",
        "url": os.environ.get(
            "COHORTOS_LOCAL_MODEL_URL_LFM",
            "https://huggingface.co/bartowski/LFM2-1.2B-Instruct-GGUF/resolve/main/LFM2-1.2B-Instruct-Q4_K_M.gguf",
        ),
        "revision": "main",
        "sha256": os.environ.get("COHORTOS_LOCAL_MODEL_SHA_LFM", ""),  # set when mirror pinned
        "approx_gb": "1.0",
        "license": "lfm1.0 (review commercial terms — not Apache)",
        "display": "LFM2.5-1.2B-Instruct (local GGUF)",
    },
    "qwen2.5-1.5b-instruct-fc": {
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "url": os.environ.get(
            "COHORTOS_LOCAL_MODEL_URL_QWEN",
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        ),
        "revision": "main",
        "sha256": os.environ.get("COHORTOS_LOCAL_MODEL_SHA_QWEN", ""),
        "approx_gb": "1.1",
        "license": "Apache-2.0",
        "display": "Qwen2.5-1.5B-Instruct-FC (local GGUF)",
    },
}

_lock = threading.Lock()
_progress: Dict[str, Any] = {
    "status": "idle",
    "pct": 0,
    "model_id": None,
    "error": None,
    "cancel": False,
}


def model_dir() -> Path:
    d = Path(os.environ.get("COHORTOS_LOCAL_MODEL_DIR") or str(Path(tempfile.gettempdir()) / "cohortos-models"))
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


def _mem_info() -> Tuple[float, float]:
    """Return (total_gb, free_gb)."""
    try:
        import psutil
        v = psutil.virtual_memory()
        return v.total / (1024**3), v.available / (1024**3)
    except Exception:
        # Conservative unknown
        return 4.0, 1.0


def ram_policy() -> Dict[str, Any]:
    total, free = _mem_info()
    if total < 5.0:
        return {
            "tier": "low",
            "total_gb": round(total, 2),
            "free_gb": round(free, 2),
            "enabled_default": False,
            "offer": False,
            "caution": "may freeze this computer; use a cloud key instead",
        }
    if total < 8.0:
        return {
            "tier": "mid",
            "total_gb": round(total, 2),
            "free_gb": round(free, 2),
            "enabled_default": False,
            "offer": True,
            "caution": "Local model may slow this PC. Prefer a cloud key on shared desks.",
        }
    return {
        "tier": "high",
        "total_gb": round(total, 2),
        "free_gb": round(free, 2),
        "enabled_default": False,  # still opt-in
        "offer": True,
        "caution": None,
    }


def disk_free_gb(path: Optional[Path] = None) -> float:
    p = path or model_dir()
    try:
        u = shutil.disk_usage(str(p))
        return u.free / (1024**3)
    except Exception:
        return 0.0


def assert_can_load(model_gb: float = 1.0, context_gb: float = 0.5) -> None:
    """Refuse load if free RAM < model + context + 1GB."""
    _, free = _mem_info()
    need = model_gb + context_gb + 1.0
    if free < need:
        raise MemoryError(
            f"Insufficient free RAM ({free:.1f}GB); need ~{need:.1f}GB for local model"
        )


def verify_model_file(path: Path, expected_sha256: str = "") -> None:
    if not expected_sha256:
        return
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    digest = h.hexdigest()
    if digest.lower() != expected_sha256.lower():
        raise ValueError(f"SHA-256 mismatch for {path.name}: got {digest[:16]}…")


def cancel_download() -> None:
    _progress["cancel"] = True


def ensure_model(
    model_id: Optional[str] = None,
    force: bool = False,
    consent: bool = False,
) -> Path:
    mid = model_id or resolve_model_id()
    meta = MODEL_REGISTRY.get(mid) or MODEL_REGISTRY["lfm2.5-1.2b-instruct"]
    path = model_dir() / meta["filename"]
    if path.is_file() and path.stat().st_size > 10_000_000 and not force:
        if meta.get("sha256"):
            verify_model_file(path, meta["sha256"])
        return path
    if os.environ.get("COHORTOS_SKIP_MODEL_DOWNLOAD") == "1":
        raise FileNotFoundError(f"Local model {mid} missing; download skipped in CI")
    if not consent:
        raise PermissionError(
            "Model download requires explicit user consent (size ~1GB; may use mobile data)"
        )
    need_gb = float(meta.get("approx_gb") or 1.0) + 0.5
    if disk_free_gb() < need_gb:
        raise OSError(f"Not enough disk space (need ~{need_gb:.1f}GB free)")
    url = os.environ.get("COHORTOS_LOCAL_MODEL_URL") or meta["url"]
    _progress.update(
        {"status": "downloading", "pct": 0, "model_id": mid, "error": None, "cancel": False}
    )
    tmp = path.with_suffix(path.suffix + ".part")
    # Resume: if .part exists, try Range (best-effort)
    headers = {}
    mode = "wb"
    existing = 0
    if tmp.is_file() and tmp.stat().st_size > 0:
        existing = tmp.stat().st_size
        headers["Range"] = f"bytes={existing}-"
        mode = "ab"

    def _hook(blocknum: int, blocksize: int, totalsize: int) -> None:
        if _progress.get("cancel"):
            raise InterruptedError("download canceled")
        total = totalsize + existing if totalsize > 0 else 0
        done = existing + blocknum * blocksize
        if total > 0:
            _progress["pct"] = min(99, int(done * 100 / total))

    try:
        req = urllib.request.Request(url, headers=headers)
        with safe_urlopen(req, timeout=120) as resp, open(tmp, mode) as out:
            while True:
                if _progress.get("cancel"):
                    raise InterruptedError("download canceled")
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                _progress["pct"] = min(99, int(_progress.get("pct") or 0) + 1)
        if meta.get("sha256"):
            verify_model_file(tmp, meta["sha256"])
        tmp.replace(path)
        _progress.update({"status": "ready", "pct": 100, "model_id": mid})
        return path
    except Exception as e:
        _progress.update({"status": "error", "error": str(e), "model_id": mid})
        raise


def delete_model(model_id: Optional[str] = None) -> bool:
    path = model_path(model_id)
    part = path.with_suffix(path.suffix + ".part")
    gone = False
    for p in (path, part):
        if p.is_file():
            p.unlink()
            gone = True
    return gone


def local_available() -> bool:
    try:
        import llama_cpp  # noqa: F401
        return True
    except Exception:
        return False


_WORKER = r'''
import json, sys
payload = json.loads(sys.stdin.read())
from llama_cpp import Llama
llm = Llama(model_path=payload["model_path"], n_ctx=int(payload.get("n_ctx") or 2048),
            n_threads=int(payload.get("n_threads") or 2), n_gpu_layers=0, verbose=False)
messages = payload.get("messages") or [{"role": "user", "content": payload.get("prompt") or ""}]
out = llm.create_chat_completion(messages=messages, max_tokens=int(payload.get("max_tokens") or 256),
                                 temperature=float(payload.get("temperature") or 0.2))
text = ((out.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
sys.stdout.write(json.dumps({"text": text}))
'''


def local_complete_isolated(
    prompt: str,
    *,
    model_id: Optional[str] = None,
    system: str = "",
    max_tokens: int = 256,
    temperature: float = 0.2,
    timeout_sec: int = 120,
    consent: bool = False,
) -> str:
    """Run inference in a subprocess (kill switch on timeout)."""
    assert_can_load()
    policy = ram_policy()
    if policy["tier"] == "low":
        raise MemoryError(policy.get("caution") or "Local model disabled on low-RAM devices")
    mid = model_id or resolve_model_id()
    try:
        path = ensure_model(mid, consent=consent or os.environ.get("COHORTOS_MODEL_CONSENT") == "1")
    except FileNotFoundError:
        raise
    if not local_available():
        raise RuntimeError("llama-cpp-python is not installed")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model_path": str(path),
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "n_ctx": 2048,
        "n_threads": max(2, (os.cpu_count() or 4) // 2),
    }
    proc = subprocess.Popen(
        [sys.executable, "-c", _WORKER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        out, err = proc.communicate(json.dumps(payload), timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        raise TimeoutError(f"Local inference killed after {timeout_sec}s")
    if proc.returncode != 0:
        raise RuntimeError(err or f"worker exit {proc.returncode}")
    data = json.loads(out or "{}")
    return str(data.get("text") or "").strip()


def local_complete(
    prompt: str,
    *,
    model_id: Optional[str] = None,
    system: str = "",
    max_tokens: int = 512,
    temperature: float = 0.2,
) -> str:
    """Public API — always isolated."""
    return local_complete_isolated(
        prompt,
        model_id=model_id,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
        consent=os.environ.get("COHORTOS_MODEL_CONSENT") == "1",
    )
