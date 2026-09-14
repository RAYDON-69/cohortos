"""
Grounded retrieval over the centre's Content Vault (SPEC §9.1 step 2).

Keyword / topic overlap only for Portion 8. Zero chunks → ungrounded.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set
import re

from models.base import TenantContext, DataAccessLayer
from models.ai import RetrievalChunk


def _tokens(text: str) -> Set[str]:
    return {t for t in re.findall(r"[a-z0-9\u0980-\u09ff]+", (text or "").lower()) if len(t) > 1}


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

    def retrieve(
        self,
        query: str,
        subject: str = "",
        topic: str = "",
        batch_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[RetrievalChunk]:
        """
        Return ranked chunks from content_resources.
        Only active resources; optional batch filter.
        """
        resources = self._list_resources()
        q_tokens = _tokens(query)
        subj = (subject or "").lower().strip()
        top = (topic or "").lower().strip()

        scored: List[RetrievalChunk] = []
        for res in resources:
            if not res.get("is_active", True):
                continue
            if batch_id:
                bids = res.get("batch_ids") or []
                if bids and batch_id not in bids:
                    continue

            title = res.get("title") or ""
            rtopic = res.get("topic") or ""
            rsubj = res.get("subject") or ""
            desc = res.get("description") or ""
            blob = f"{title} {rtopic} {rsubj} {desc}"

            score = 0.0
            r_tokens = _tokens(blob)
            if q_tokens and r_tokens:
                overlap = len(q_tokens & r_tokens)
                score += overlap / max(len(q_tokens), 1)
            if subj and subj in (rsubj.lower(), title.lower(), rtopic.lower()):
                score += 0.5
            if top and top in (rtopic.lower(), title.lower(), desc.lower()):
                score += 0.8
            if score <= 0:
                continue

            excerpt = (desc or title)[:400]
            scored.append(
                RetrievalChunk(
                    resource_id=str(res.get("id") or ""),
                    title=title,
                    topic=rtopic,
                    subject=rsubj,
                    excerpt=excerpt,
                    score=round(score, 4),
                )
            )

        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:limit]

    def _list_resources(self) -> List[Dict[str, Any]]:
        if self.content_service and hasattr(self.content_service, "list_resources"):
            try:
                return self.content_service.list_resources(active_only=True) or []
            except Exception:
                pass
        return self.data_layer.get_all("content_resources") or []
