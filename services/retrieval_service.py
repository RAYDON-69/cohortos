"""
Grounded retrieval over Content Vault — chunked BM25-style ranking (Phase 8).

Pure Python, offline, no native vector extension. Scales to many long documents
via paragraph/window chunking + term scoring. sqlite-vec / LanceDB = future upgrade
when embeddings + native load are acceptable.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import math
import re

from models.base import TenantContext, DataAccessLayer
from models.ai import RetrievalChunk


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9\u0980-\u09ff]+", (text or "").lower()) if len(t) > 1]


def _chunk_text(text: str, max_chars: int = 900, overlap: int = 120) -> List[str]:
    """Split long docs into overlapping windows; prefer paragraph boundaries."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    paras = re.split(r"\n\s*\n", text)
    chunks: List[str] = []
    buf = ""
    for p in paras:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) + 1 <= max_chars:
            buf = f"{buf}\n\n{p}".strip() if buf else p
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= max_chars:
                buf = p
            else:
                # hard window
                start = 0
                while start < len(p):
                    end = min(len(p), start + max_chars)
                    chunks.append(p[start:end])
                    start = max(end - overlap, start + 1)
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks or [text[:max_chars]]


class RetrievalService:
    """NotebookLM-style scoped retrieval over Vault resources for one tenant."""

    def __init__(
        self,
        tenant_context: TenantContext,
        data_layer: Optional[DataAccessLayer] = None,
        content_service=None,
    ):
        self.tenant_context = tenant_context
        self.data_layer = data_layer or DataAccessLayer(tenant_context)
        self.content_service = content_service
        self._chunk_cache: Optional[List[Dict[str, Any]]] = None

    def invalidate_cache(self) -> None:
        self._chunk_cache = None

    def _list_resources(self) -> List[Dict[str, Any]]:
        if self.content_service and hasattr(self.content_service, "list_resources"):
            try:
                return list(self.content_service.list_resources() or [])
            except Exception:
                pass
        try:
            return list(self.data_layer.get_all("content_resources") or [])
        except Exception:
            return []

    def _resource_body(self, res: Dict[str, Any]) -> str:
        parts = [
            res.get("title") or "",
            res.get("topic") or "",
            res.get("subject") or "",
            res.get("description") or "",
            res.get("text_content") or res.get("body") or res.get("excerpt") or "",
        ]
        return "\n".join(str(p) for p in parts if p)

    def _build_chunks(self, batch_id: Optional[str] = None) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for res in self._list_resources():
            if not res.get("is_active", True):
                continue
            if batch_id:
                bids = res.get("batch_ids") or []
                if bids and batch_id not in bids:
                    continue
            body = self._resource_body(res)
            rid = str(res.get("id") or res.get("resource_id") or "")
            title = res.get("title") or rid
            for i, ch in enumerate(_chunk_text(body)):
                toks = _tokens(ch)
                out.append(
                    {
                        "resource_id": rid,
                        "title": title,
                        "chunk_index": i,
                        "text": ch,
                        "tokens": toks,
                        "tf": self._tf(toks),
                    }
                )
        return out

    @staticmethod
    def _tf(toks: List[str]) -> Dict[str, float]:
        n = len(toks) or 1
        counts: Dict[str, int] = {}
        for t in toks:
            counts[t] = counts.get(t, 0) + 1
        return {t: c / n for t, c in counts.items()}

    def _idf(self, chunks: List[Dict[str, Any]]) -> Dict[str, float]:
        N = len(chunks) or 1
        df: Dict[str, int] = {}
        for ch in chunks:
            for t in set(ch["tokens"]):
                df[t] = df.get(t, 0) + 1
        return {t: math.log(1 + N / (1 + d)) for t, d in df.items()}

    def retrieve(
        self,
        query: str,
        subject: str = "",
        topic: str = "",
        batch_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[RetrievalChunk]:
        chunks = self._build_chunks(batch_id=batch_id)
        if not chunks:
            return []
        q_tokens = _tokens(query)
        if subject:
            q_tokens += _tokens(subject)
        if topic:
            q_tokens += _tokens(topic)
        if not q_tokens:
            return []
        idf = self._idf(chunks)
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for ch in chunks:
            score = 0.0
            tf = ch["tf"]
            for t in q_tokens:
                if t in tf:
                    score += (tf[t] * idf.get(t, 0.0)) * (1.0 + 0.1 * q_tokens.count(t))
            # title boost
            title_toks = set(_tokens(ch.get("title") or ""))
            if title_toks & set(q_tokens):
                score += 0.35
            if score > 0:
                scored.append((score, ch))
        scored.sort(key=lambda x: x[0], reverse=True)
        results: List[RetrievalChunk] = []
        for score, ch in scored[: max(1, limit)]:
            results.append(
                RetrievalChunk(
                    resource_id=ch["resource_id"],
                    title=ch["title"],
                    excerpt=(ch["text"] or "")[:400],
                    score=float(score),
                )
            )
        return results
