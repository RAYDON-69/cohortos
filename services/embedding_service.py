"""
Local offline embeddings without GPU or native vector DB (Phase 9).

Approach: high-dimensional sparse-ish vectors from word unigrams + character
trigrams, L2-normalized, cosine nearest-neighbor via numpy (or pure Python).
Education synonym expansion improves paraphrase matching without a neural model.

Not as strong as MiniLM/BGE — but real continuous vectors + cosine, not BM25-only.
Upgrade path: swap embed() for onnx MiniLM when model download is acceptable.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Dict, List, Sequence, Tuple

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None  # type: ignore

DIM = 384

# Coaching / science paraphrase map (query side expansion)
SYNONYMS: Dict[str, List[str]] = {
    "fast": ["rate", "speed", "kinetics", "quick"],
    "faster": ["rate", "kinetics", "temperature"],
    "slow": ["rate", "kinetics"],
    "reaction": ["kinetics", "chemical", "react"],
    "temperature": ["arrhenius", "heat", "thermal", "activation"],
    "rises": ["increase", "temperature", "heat"],
    "proceed": ["rate", "reaction", "kinetics"],
    "how": [],
    "does": [],
    "when": [],
    "energy": ["activation", "arrhenius"],
    "speed": ["rate", "kinetics"],
    "concentration": ["rate", "order", "molarity"],
}


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9\u0980-\u09ff]+", (text or "").lower()) if len(t) > 1]


def _expand(tokens: List[str]) -> List[str]:
    out = list(tokens)
    for t in tokens:
        for s in SYNONYMS.get(t, []):
            out.append(s)
    return out


def _hash_idx(s: str, dim: int = DIM) -> int:
    h = hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "little") % dim


def embed_text(text: str, dim: int = DIM) -> List[float]:
    """Deterministic local embedding — word + char-trigram features."""
    toks = _expand(_tokens(text))
    if HAS_NUMPY:
        v = np.zeros(dim, dtype=np.float64)
    else:
        v = [0.0] * dim
    for t in toks:
        i = _hash_idx("w:" + t, dim)
        if HAS_NUMPY:
            v[i] += 1.0
        else:
            v[i] += 1.0
        # char trigrams for morphology
        padded = f"#{t}#"
        for j in range(len(padded) - 2):
            tri = padded[j : j + 3]
            k = _hash_idx("c:" + tri, dim)
            if HAS_NUMPY:
                v[k] += 0.35
            else:
                v[k] += 0.35
    # L2 normalize
    if HAS_NUMPY:
        n = float(np.linalg.norm(v))
        if n > 1e-12:
            v = v / n
        return v.tolist()
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


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
