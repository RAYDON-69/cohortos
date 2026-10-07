"""In-memory / SQLite-simple adapter for parity tests (no Chroma server)."""
from __future__ import annotations
import math
import re
from collections import Counter
from typing import Any, Dict, List, Sequence
from services.vectorstores.base import VectorStore

def _tokens(s: str) -> Counter:
    return Counter(re.findall(r"\w+", (s or "").lower()))

def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[t] * b[t] for t in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

class MemoryVectorStore(VectorStore):
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self._rows: List[Dict[str, Any]] = []

    def add(self, ids: Sequence[str], documents: Sequence[str], metadatas: Sequence[Dict[str, Any]] | None = None) -> None:
        metas = list(metadatas or [{}] * len(ids))
        for i, doc, meta in zip(ids, documents, metas):
            self._rows.append({"id": i, "document": doc, "metadata": dict(meta), "tok": _tokens(doc)})

    def query(self, text: str, n: int = 5) -> List[Dict[str, Any]]:
        q = _tokens(text)
        scored = [({**{k: r[k] for k in ("id", "document", "metadata")}, "score": _cosine(q, r["tok"])}) for r in self._rows]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:n]

    def count(self) -> int:
        return len(self._rows)
