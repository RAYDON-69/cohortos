"""Hybrid retrieval: semantic cosine embeddings + BM25 (Phase 9)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import math
import re

from models.base import TenantContext, DataAccessLayer
from models.ai import RetrievalChunk
from services.embedding_service import embed_text, cosine, top_k


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9\u0980-\u09ff]+", (text or "").lower()) if len(t) > 1]


def _chunk_text(text: str, max_chars: int = 900, overlap: int = 120) -> List[str]:
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
    def __init__(self, tenant_context: TenantContext, data_layer=None, content_service=None):
        self.tenant_context = tenant_context
        self.data_layer = data_layer or DataAccessLayer(tenant_context)
        self.content_service = content_service

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
        return "\n".join(
            str(p)
            for p in [
                res.get("title") or "",
                res.get("topic") or "",
                res.get("subject") or "",
                res.get("description") or "",
                res.get("text_content") or res.get("body") or "",
            ]
            if p
        )

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
                        "vec": embed_text(f"{title}\n{ch}"),
                    }
                )
        return out

    def _bm25_scores(self, query: str, chunks: List[Dict[str, Any]]) -> Dict[int, float]:
        q = _tokens(query)
        if not q or not chunks:
            return {}
        N = len(chunks)
        df: Dict[str, int] = {}
        for ch in chunks:
            for t in set(ch["tokens"]):
                df[t] = df.get(t, 0) + 1
        idf = {t: math.log(1 + N / (1 + d)) for t, d in df.items()}
        scores: Dict[int, float] = {}
        for i, ch in enumerate(chunks):
            tf: Dict[str, float] = {}
            n = len(ch["tokens"]) or 1
            for t in ch["tokens"]:
                tf[t] = tf.get(t, 0) + 1 / n
            s = 0.0
            for t in q:
                if t in tf:
                    s += tf[t] * idf.get(t, 0)
            scores[i] = s
        return scores

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
        qtext = " ".join(x for x in [query, subject, topic] if x)
        qvec = embed_text(qtext)
        bm25 = self._bm25_scores(qtext, chunks)
        ranked: List[Tuple[float, Dict[str, Any]]] = []
        for i, ch in enumerate(chunks):
            sem = cosine(qvec, ch["vec"])
            lex = bm25.get(i, 0.0)
            # Hybrid: semantic primary, BM25 secondary
            score = 0.65 * sem + 0.35 * (lex / (1.0 + lex))
            if score > 0.02:
                ranked.append((score, ch))
        ranked.sort(key=lambda x: x[0], reverse=True)
        results: List[RetrievalChunk] = []
        for score, ch in ranked[: max(1, limit)]:
            results.append(
                RetrievalChunk(
                    resource_id=ch["resource_id"],
                    title=ch["title"],
                    excerpt=(ch["text"] or "")[:400],
                    score=float(score),
                )
            )
        return results
