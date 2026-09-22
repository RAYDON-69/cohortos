"""
Embeddings for Vault retrieval (Phase 10).

Primary: quantized ONNX all-MiniLM-L6-v2 (~23MB) via onnxruntime CPU.
Fallback: hashing word+char-trigram vectors (Phase 9) if model missing.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None  # type: ignore

DIM = 384
_MODEL_DIR = Path(os.environ.get("COHORTOS_EMBED_MODEL_DIR") or Path(__file__).resolve().parent.parent / "models" / "minilm")
_session = None
_tokenizer = None
_backend = "hash"


def _find_onnx() -> Optional[Path]:
    for name in (
        "model_qint8_arm64.onnx",
        "model_qint8.onnx",
        "model_qint8_avx2.onnx",
        "model.onnx",
    ):
        p = _MODEL_DIR / name
        if p.exists() and p.stat().st_size > 1_000_000:
            return p
    return None


def backend_name() -> str:
    _ensure_neural()
    return _backend


def _ensure_neural() -> bool:
    global _session, _tokenizer, _backend
    if _session is not None:
        return _backend == "onnx"
    onnx_path = _find_onnx()
    tok_path = _MODEL_DIR / "tokenizer.json"
    if not onnx_path or not tok_path.exists():
        _backend = "hash"
        return False
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        _session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        _tokenizer = Tokenizer.from_file(str(tok_path))
        _backend = "onnx"
        return True
    except Exception:
        _session = None
        _tokenizer = None
        _backend = "hash"
        return False


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9\u0980-\u09ff]+", (text or "").lower()) if len(t) > 1]


SYNONYMS: Dict[str, List[str]] = {
    "fast": ["rate", "speed", "kinetics", "quick"],
    "faster": ["rate", "kinetics", "temperature"],
    "slow": ["rate", "kinetics"],
    "reaction": ["kinetics", "chemical", "react"],
    "temperature": ["arrhenius", "heat", "thermal", "activation"],
    "rises": ["increase", "temperature", "heat"],
    "proceed": ["rate", "reaction", "kinetics"],
    "energy": ["activation", "arrhenius"],
    "speed": ["rate", "kinetics"],
    "concentration": ["rate", "order", "molarity"],
}


def _expand(tokens: List[str]) -> List[str]:
    out = list(tokens)
    for t in tokens:
        out.extend(SYNONYMS.get(t, []))
    return out


def _hash_idx(s: str, dim: int = DIM) -> int:
    h = hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "little") % dim


def _embed_hash(text: str, dim: int = DIM) -> List[float]:
    toks = _expand(_tokens(text))
    if HAS_NUMPY:
        v = np.zeros(dim, dtype=np.float64)
    else:
        v = [0.0] * dim
    for t in toks:
        i = _hash_idx("w:" + t, dim)
        v[i] = v[i] + 1.0 if not HAS_NUMPY else v[i] + 1.0
        padded = f"#{t}#"
        for j in range(max(0, len(padded) - 2)):
            k = _hash_idx("c:" + padded[j : j + 3], dim)
            if HAS_NUMPY:
                v[k] += 0.35
            else:
                v[k] += 0.35
    if HAS_NUMPY:
        n = float(np.linalg.norm(v))
        if n > 1e-12:
            v = v / n
        return v.tolist()
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _embed_onnx(text: str) -> List[float]:
    assert _session is not None and _tokenizer is not None
    enc = _tokenizer.encode(text or "")
    ids = enc.ids[:128]
    pad = 128 - len(ids)
    import numpy as np

    ids_a = np.array([ids + [0] * pad], dtype=np.int64)
    mask = np.array([[1] * len(ids) + [0] * pad], dtype=np.int64)
    tt = np.zeros_like(ids_a)
    last = _session.run(
        None, {"input_ids": ids_a, "attention_mask": mask, "token_type_ids": tt}
    )[0]
    emb = (last * mask[:, :, None]).sum(1) / np.maximum(mask.sum(1, keepdims=True), 1)
    emb = emb[0]
    emb = emb / (np.linalg.norm(emb) + 1e-9)
    return emb.tolist()


def embed_text(text: str, dim: int = DIM) -> List[float]:
    if _ensure_neural():
        try:
            return _embed_onnx(text)
        except Exception:
            return _embed_hash(text, dim)
    return _embed_hash(text, dim)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if HAS_NUMPY:
        return float(np.dot(a, b))
    return sum(x * y for x, y in zip(a, b))


def top_k(
    query_vec: Sequence[float],
    corpus: List[Tuple[Sequence[float], object]],
    k: int = 5,
) -> List[Tuple[float, object]]:
    scored = [(cosine(query_vec, vec), meta) for vec, meta in corpus]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:k]
