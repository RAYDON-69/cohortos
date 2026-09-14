"""
Per-student daily AI query caps + cache helpers (SPEC §9.3).
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime, timezone
import uuid

from models.base import TenantContext, DataAccessLayer
from models.ai import (
    StudentQuotaUsage,
    QueryCacheEntry,
    query_hash,
    normalize_query,
    DEFAULT_DAILY_MCQ_CAP,
    DEFAULT_DAILY_WRITTEN_CAP,
    QTYPE_MCQ,
    QTYPE_WRITTEN,
    QTYPE_CQ,
)
from services.config_service import ConfigService


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class QuotaExceededError(Exception):
    def __init__(self, student_id: str, qtype: str, cap: int):
        self.student_id = student_id
        self.qtype = qtype
        self.cap = cap
        super().__init__(f"Daily {qtype} cap ({cap}) exceeded for student {student_id}")


class AIQuotaService:
    def __init__(
        self,
        tenant_context: TenantContext,
        data_layer: Optional[DataAccessLayer] = None,
        config_service: Optional[ConfigService] = None,
    ):
        self.tenant_context = tenant_context
        self.data_layer = data_layer or DataAccessLayer(tenant_context)
        self.config_service = config_service or ConfigService(tenant_context)

    def get_caps(self) -> Dict[str, int]:
        return {
            "mcq": int(
                self.config_service.get("ai.daily_mcq_cap", DEFAULT_DAILY_MCQ_CAP)
                or DEFAULT_DAILY_MCQ_CAP
            ),
            "written": int(
                self.config_service.get("ai.daily_written_cap", DEFAULT_DAILY_WRITTEN_CAP)
                or DEFAULT_DAILY_WRITTEN_CAP
            ),
        }

    def set_caps(self, mcq: Optional[int] = None, written: Optional[int] = None) -> None:
        if mcq is not None:
            self.config_service.set("ai.daily_mcq_cap", int(mcq))
        if written is not None:
            self.config_service.set("ai.daily_written_cap", int(written))

    def _usage_record(self, student_id: str, date: Optional[str] = None) -> Dict[str, Any]:
        date = date or _today()
        for row in self.data_layer.get_all("ai_quota_usage"):
            if row.get("student_id") == student_id and row.get("date") == date:
                return row
        usage = StudentQuotaUsage(
            tenant_id=str(self.tenant_context.tenant_id),
            student_id=student_id,
            date=date,
        )
        rid = self.data_layer.create("ai_quota_usage", usage.to_dict())
        return self.data_layer.get("ai_quota_usage", rid) or usage.to_dict()

    def check_and_increment(self, student_id: str, question_type: str) -> Dict[str, Any]:
        """
        Enforce daily cap then increment. Raises QuotaExceededError.
        MCQ uses mcq bucket; written/cq use written bucket.
        """
        caps = self.get_caps()
        bucket = "mcq" if question_type == QTYPE_MCQ else "written"
        cap = caps[bucket]
        rec = self._usage_record(student_id)
        count_key = "mcq_count" if bucket == "mcq" else "written_count"
        current = int(rec.get(count_key) or 0)
        if current >= cap:
            raise QuotaExceededError(student_id, bucket, cap)
        updates = {
            count_key: current + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.data_layer.update("ai_quota_usage", uuid.UUID(rec["id"]), updates)
        rec.update(updates)
        return rec

    def get_usage(self, student_id: str, date: Optional[str] = None) -> Dict[str, Any]:
        return self._usage_record(student_id, date)

    # ── Cache ─────────────────────────────────────────────────────────

    def cache_get(self, query: str, subject: str = "") -> Optional[Dict[str, Any]]:
        h = query_hash(query, subject)
        for row in self.data_layer.get_all("ai_query_cache"):
            if row.get("query_hash") == h:
                # bump hit
                hits = int(row.get("hit_count") or 0) + 1
                self.data_layer.update(
                    "ai_query_cache",
                    uuid.UUID(row["id"]),
                    {"hit_count": hits, "updated_at": datetime.now(timezone.utc).isoformat()},
                )
                row["hit_count"] = hits
                return row
        return None

    def cache_put(
        self,
        query: str,
        subject: str,
        answer_block: str,
        how_block: str,
        why_block: str,
        confidence: float,
        source_chunk_ids: Optional[list] = None,
    ) -> str:
        h = query_hash(query, subject)
        existing = self.cache_get(query, subject)
        if existing:
            return existing["id"]
        entry = QueryCacheEntry(
            tenant_id=str(self.tenant_context.tenant_id),
            query_hash=h,
            query_normalized=normalize_query(query),
            subject=subject or "",
            answer_block=answer_block,
            how_block=how_block,
            why_block=why_block,
            confidence=confidence,
            source_chunk_ids=list(source_chunk_ids or []),
        )
        rid = self.data_layer.create("ai_query_cache", entry.to_dict())
        return str(rid)
