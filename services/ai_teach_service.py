"""
CohortOS Teach — teacher AI co-pilot (SPEC §9.2).

Hard rules:
- Never auto-publish to students; everything goes through review queue.
- Ungrounded / low-confidence items stay needs_review.
- Version history retained on accept/edit/reject.
- OCR assist is a stub only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid

from models.base import TenantContext, DataAccessLayer
from models.ai import (
    AIGeneratedItem,
    TeacherStyleProfile,
    STATUS_DRAFT,
    STATUS_NEEDS_REVIEW,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_EDITED,
    DEFAULT_CONFIDENCE_THRESHOLD,
    QTYPE_MCQ,
    QTYPE_WRITTEN,
    TIER_CHEAP,
    TIER_PREMIUM,
)
from services.config_service import ConfigService
from services.audit_service import AuditService
from services.llm_provider import (
    LLMProvider,
    MockLLMProvider,
    LLMRequest,
    RateLimitError,
    OfflineError,
    parse_answer_blocks,
)
from services.retrieval_service import RetrievalService


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class OCRNotImplementedError(Exception):
    """OCR assist is optional and stubbed for Portion 8."""


class AITeachService:
    def __init__(
        self,
        tenant_context: TenantContext,
        data_layer: Optional[DataAccessLayer] = None,
        config_service: Optional[ConfigService] = None,
        audit_service: Optional[AuditService] = None,
        llm: Optional[LLMProvider] = None,
        retrieval: Optional[RetrievalService] = None,
        content_service=None,
        exam_service=None,
    ):
        self.tenant_context = tenant_context
        self.data_layer = data_layer or DataAccessLayer(tenant_context)
        self.config_service = config_service or ConfigService(tenant_context)
        self.audit_service = audit_service or AuditService(tenant_context)
        self.llm = llm or MockLLMProvider()
        self.retrieval = retrieval or RetrievalService(
            tenant_context, self.data_layer, content_service=content_service
        )
        self.content_service = content_service
        self.exam_service = exam_service

    def confidence_threshold(self) -> float:
        return float(
            self.config_service.get("ai.confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD)
            or DEFAULT_CONFIDENCE_THRESHOLD
        )

    # ── Style profile [BULLET] ────────────────────────────────────────

    def upsert_style_profile(
        self,
        subject: str,
        style_notes: str = "",
        terminology: Optional[List[str]] = None,
        sign_conventions: str = "",
        difficulty: str = "medium",
        few_shot_examples: Optional[List[Dict[str, str]]] = None,
        preferred_language: str = "en",
        actor_id: str = "",
    ) -> Dict[str, Any]:
        existing = None
        for row in self.data_layer.get_all("ai_style_profiles"):
            if row.get("subject") == subject and row.get("is_active", True):
                existing = row
                break
        if existing:
            updates = {
                "style_notes": style_notes,
                "terminology": list(terminology or existing.get("terminology") or []),
                "sign_conventions": sign_conventions or existing.get("sign_conventions") or "",
                "difficulty": difficulty,
                "few_shot_examples": list(
                    few_shot_examples or existing.get("few_shot_examples") or []
                ),
                "preferred_language": preferred_language,
                "version": int(existing.get("version") or 1) + 1,
                "updated_at": _utcnow(),
            }
            self.data_layer.update(
                "ai_style_profiles", uuid.UUID(existing["id"]), updates
            )
            existing.update(updates)
            return existing
        profile = TeacherStyleProfile(
            tenant_id=str(self.tenant_context.tenant_id),
            subject=subject,
            style_notes=style_notes,
            terminology=list(terminology or []),
            sign_conventions=sign_conventions,
            difficulty=difficulty,
            few_shot_examples=list(few_shot_examples or []),
            preferred_language=preferred_language,
            created_by=actor_id,
        )
        rid = self.data_layer.create("ai_style_profiles", profile.to_dict())
        return self.data_layer.get("ai_style_profiles", rid) or profile.to_dict()

    def list_style_profiles(self) -> List[Dict[str, Any]]:
        return [r for r in self.data_layer.get_all("ai_style_profiles") if r.get("is_active", True)]

    def get_style_profile(self, subject: str) -> Optional[Dict[str, Any]]:
        for row in self.data_layer.get_all("ai_style_profiles"):
            if row.get("subject") == subject and row.get("is_active", True):
                return row
        return None

    # ── Generation (always → review queue) ────────────────────────────

    def generate_item(
        self,
        item_type: str,
        subject: str,
        topic: str,
        prompt: str,
        actor_id: str = "",
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a draft item. Always starts as needs_review or draft.
        Never approved automatically [BULLET].
        """
        chunks = self.retrieval.retrieve(
            query=prompt or topic, subject=subject, topic=topic, batch_id=batch_id, limit=5
        )
        grounded = len(chunks) > 0
        chunk_ids = [c.resource_id for c in chunks]
        profile = self.get_style_profile(subject)

        content: Dict[str, Any] = {}
        confidence = 0.0
        review_reason = ""
        status = STATUS_NEEDS_REVIEW

        try:
            style_bits = ""
            if profile:
                style_bits = (
                    f"Style: {profile.get('style_notes')}; "
                    f"Terms: {profile.get('terminology')}; "
                    f"Signs: {profile.get('sign_conventions')}; "
                    f"Lang: {profile.get('preferred_language')}"
                )
            context = "\n".join(f"[{c.resource_id}] {c.excerpt}" for c in chunks) or "(none)"
            system = (
                "You are CohortOS Teach. Generate ONLY from provided sources. "
                "Never invent syllabus content outside sources. "
                f"{style_bits}"
            )
            tier = TIER_CHEAP if item_type == QTYPE_MCQ else TIER_PREMIUM
            resp = self.llm.complete(
                LLMRequest(
                    prompt=(
                        f"Item type: {item_type}\nSubject: {subject}\nTopic: {topic}\n"
                        f"Sources:\n{context}\n\nRequest: {prompt}"
                    ),
                    system=system,
                    tier=tier,
                )
            )
            blocks = parse_answer_blocks(resp.text)
            content = {
                "raw": resp.text,
                "answer": blocks.get("answer") or "",
                "how": blocks.get("how") or "",
                "why": blocks.get("why") or "",
                "item_type": item_type,
            }
            confidence = 0.55 + (0.25 if grounded else 0.0) + (0.1 if blocks.get("answer") else 0)
            confidence = min(1.0, round(confidence, 3))
            if not grounded:
                review_reason = "ungrounded — needs teacher review"
                status = STATUS_NEEDS_REVIEW
            elif confidence < self.confidence_threshold():
                review_reason = f"low confidence ({confidence:.2f})"
                status = STATUS_NEEDS_REVIEW
            else:
                # Still never auto-approved
                status = STATUS_NEEDS_REVIEW
                review_reason = "awaiting teacher approval"
        except (RateLimitError, OfflineError) as e:
            content = {"error": str(e)}
            review_reason = f"provider_unavailable: {e}"
            status = STATUS_NEEDS_REVIEW
            confidence = 0.0

        item = AIGeneratedItem(
            tenant_id=str(self.tenant_context.tenant_id),
            item_type=item_type,
            subject=subject,
            topic=topic,
            content=content,
            status=status,
            confidence=confidence,
            grounded=grounded,
            source_chunk_ids=chunk_ids,
            review_reason=review_reason,
            created_by=actor_id or "system",
            history=[{
                "action": "create",
                "at": _utcnow(),
                "by": actor_id or "system",
                "status": status,
            }],
        )
        rid = self.data_layer.create("ai_generated_items", item.to_dict())
        stored = self.data_layer.get("ai_generated_items", rid) or item.to_dict()
        if self.audit_service:
            self.audit_service.log_create(
                table_name="ai_generated_items",
                record_id=rid,
                new_state=stored,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
        return stored

    def generate_analytics_suggestion(
        self,
        subject: str,
        topic: str,
        cohort_size: int = 3,
        weakness_severity: float = 0.8,
        actor_id: str = "",
    ) -> Dict[str, Any]:
        """High-signal analytics [BULLET]: ranked by cohort × severity."""
        impact = float(cohort_size) * float(weakness_severity)
        item = self.generate_item(
            item_type="analytics",
            subject=subject,
            topic=topic,
            prompt=(
                f"misconception analytics for topic {topic}; "
                f"cohort_size={cohort_size}; severity={weakness_severity}"
            ),
            actor_id=actor_id,
        )
        # attach impact
        self.data_layer.update(
            "ai_generated_items",
            uuid.UUID(item["id"]),
            {"impact_score": impact, "updated_at": _utcnow()},
        )
        item["impact_score"] = impact
        return item

    # ── Review gate [BULLET] ──────────────────────────────────────────

    def list_review_queue(
        self, status: str = STATUS_NEEDS_REVIEW, limit: int = 50
    ) -> List[Dict[str, Any]]:
        items = [
            i
            for i in self.data_layer.get_all("ai_generated_items")
            if i.get("status") == status
        ]
        items.sort(key=lambda x: (-float(x.get("impact_score") or 0), x.get("created_at") or ""))
        return items[:limit]

    def approve_item(
        self, item_id: str, actor_id: str, edits: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        item = self.data_layer.get("ai_generated_items", uuid.UUID(item_id))
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        history = list(item.get("history") or [])
        history.append({
            "action": "approve" if not edits else "edit_approve",
            "at": _utcnow(),
            "by": actor_id,
            "status": STATUS_APPROVED,
        })
        updates: Dict[str, Any] = {
            "status": STATUS_APPROVED,
            "approved_by": actor_id,
            "approved_at": _utcnow(),
            "version": int(item.get("version") or 1) + (1 if edits else 0),
            "history": history,
            "updated_at": _utcnow(),
        }
        if edits:
            content = dict(item.get("content") or {})
            content.update(edits)
            updates["content"] = content
            updates["status"] = STATUS_APPROVED
        self.data_layer.update("ai_generated_items", uuid.UUID(item_id), updates)
        item.update(updates)
        if self.audit_service:
            self.audit_service.log_update(
                table_name="ai_generated_items",
                record_id=uuid.UUID(item_id),
                old_state={},
                new_state=item,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
        return item

    def reject_item(
        self, item_id: str, actor_id: str, reason: str = ""
    ) -> Dict[str, Any]:
        item = self.data_layer.get("ai_generated_items", uuid.UUID(item_id))
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        history = list(item.get("history") or [])
        history.append({
            "action": "reject",
            "at": _utcnow(),
            "by": actor_id,
            "status": STATUS_REJECTED,
            "reason": reason,
        })
        updates = {
            "status": STATUS_REJECTED,
            "rejected_by": actor_id,
            "rejected_at": _utcnow(),
            "reject_reason": reason,
            "history": history,
            "updated_at": _utcnow(),
        }
        self.data_layer.update("ai_generated_items", uuid.UUID(item_id), updates)
        item.update(updates)
        return item

    def student_visible_items(
        self, subject: str = "", topic: str = ""
    ) -> List[Dict[str, Any]]:
        """Only approved items may reach students [BULLET]."""
        out = []
        for i in self.data_layer.get_all("ai_generated_items"):
            if i.get("status") != STATUS_APPROVED:
                continue
            if subject and i.get("subject") != subject:
                continue
            if topic and i.get("topic") != topic:
                continue
            out.append(i)
        return out

    def push_to_exam_bank(
        self, item_id: str, actor_id: str
    ) -> Dict[str, Any]:
        """Push approved item toward exam module (metadata link only)."""
        item = self.data_layer.get("ai_generated_items", uuid.UUID(item_id))
        if not item:
            raise ValueError("Item not found")
        if item.get("status") != STATUS_APPROVED:
            raise ValueError("Only approved items can be pushed to exam bank")
        content = dict(item.get("content") or {})
        content["pushed_to_exam_bank"] = True
        content["pushed_at"] = _utcnow()
        content["pushed_by"] = actor_id
        self.data_layer.update(
            "ai_generated_items",
            uuid.UUID(item_id),
            {"content": content, "updated_at": _utcnow()},
        )
        item["content"] = content
        return item

    # ── OCR stub [NEW optional] ───────────────────────────────────────

    def ocr_grade_handwriting(
        self,
        image_ref: str,
        rubric: Optional[Dict[str, Any]] = None,
        actor_id: str = "",
    ) -> Dict[str, Any]:
        """
        Optional OCR assist — stub only. Always returns needs teacher review.
        Handwritten AI OCR is deprecated from Exam module roadmap in favour of OMR.
        """
        return {
            "ok": False,
            "status": STATUS_NEEDS_REVIEW,
            "message": "needs teacher review / not implemented",
            "image_ref": image_ref,
            "transcription": None,
            "grade": None,
            "conceptual_flags": [],
            "actor_id": actor_id,
        }
