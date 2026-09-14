"""
CohortOS Solve — student-facing AI tutor pipeline (SPEC §9.1).

Pipeline: classify → retrieve → generate → self-verify → confidence →
quota/cache → persist thread message. Offline / 429 degrade to queued notice.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid

from models.base import TenantContext, DataAccessLayer
from models.ai import (
    AIThread,
    AIMessage,
    RetrievalChunk,
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
    parse_classification,
)
from services.retrieval_service import RetrievalService
from services.ai_quota_service import AIQuotaService, QuotaExceededError


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class SolveResult:
    """Structured result returned to callers / UI."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)


class AISolveService:
    def __init__(
        self,
        tenant_context: TenantContext,
        data_layer: Optional[DataAccessLayer] = None,
        config_service: Optional[ConfigService] = None,
        audit_service: Optional[AuditService] = None,
        llm: Optional[LLMProvider] = None,
        retrieval: Optional[RetrievalService] = None,
        quota: Optional[AIQuotaService] = None,
        content_service=None,
    ):
        self.tenant_context = tenant_context
        self.data_layer = data_layer or DataAccessLayer(tenant_context)
        self.config_service = config_service or ConfigService(tenant_context)
        self.audit_service = audit_service or AuditService(tenant_context)
        self.llm = llm or MockLLMProvider()
        self.retrieval = retrieval or RetrievalService(
            tenant_context, self.data_layer, content_service=content_service
        )
        self.quota = quota or AIQuotaService(
            tenant_context, self.data_layer, self.config_service
        )

    def confidence_threshold(self) -> float:
        return float(
            self.config_service.get("ai.confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD)
            or DEFAULT_CONFIDENCE_THRESHOLD
        )

    # ── Threads ───────────────────────────────────────────────────────

    def get_or_create_thread(
        self,
        student_id: str,
        subject: str = "",
        topic: str = "",
        title: str = "",
    ) -> Dict[str, Any]:
        for row in self.data_layer.get_all("ai_threads"):
            if (
                row.get("student_id") == student_id
                and row.get("is_active", True)
                and (not subject or row.get("subject") == subject)
            ):
                return row
        thread = AIThread(
            tenant_id=str(self.tenant_context.tenant_id),
            student_id=student_id,
            subject=subject,
            topic=topic,
            title=title or (topic or subject or "Solve session"),
        )
        rid = self.data_layer.create("ai_threads", thread.to_dict())
        return self.data_layer.get("ai_threads", rid) or thread.to_dict()

    def list_threads(self, student_id: str) -> List[Dict[str, Any]]:
        return [
            t
            for t in self.data_layer.get_all("ai_threads")
            if t.get("student_id") == student_id and t.get("is_active", True)
        ]

    def list_messages(self, thread_id: str) -> List[Dict[str, Any]]:
        msgs = [
            m
            for m in self.data_layer.get_all("ai_messages")
            if m.get("thread_id") == thread_id
        ]
        msgs.sort(key=lambda m: m.get("created_at") or "")
        return msgs

    def annotate_message(
        self, message_id: str, annotation: str, teacher_id: str
    ) -> Dict[str, Any]:
        msg = self.data_layer.get("ai_messages", uuid.UUID(message_id))
        if not msg:
            raise ValueError(f"Message not found: {message_id}")
        updates = {
            "teacher_annotation": annotation,
            "updated_at": _utcnow(),
        }
        self.data_layer.update("ai_messages", uuid.UUID(message_id), updates)
        msg.update(updates)
        if self.audit_service:
            self.audit_service.log_update(
                table_name="ai_messages",
                record_id=uuid.UUID(message_id),
                old_state={},
                new_state=msg,
                actor_id=uuid.UUID(teacher_id) if teacher_id else self.tenant_context.tenant_id,
            )
        return msg

    # ── Main pipeline ─────────────────────────────────────────────────

    def ask(
        self,
        student_id: str,
        question: str,
        subject: str = "",
        topic: str = "",
        board: str = "",
        question_type: Optional[str] = None,
        thread_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        skip_quota: bool = False,
    ) -> SolveResult:
        """
        Full Solve pipeline. Never raises on LLM failure — returns degraded
        result with needs_review / queued flags instead.
        """
        if not question or not question.strip():
            raise ValueError("question is required")
        if not student_id:
            raise ValueError("student_id is required")

        # 1. Classification
        classification = self._classify(question, subject, topic, board, question_type)
        qtype = classification["question_type"]
        subject = classification["subject"] or subject
        topic = classification["topic"] or topic
        board = classification["board"] or board

        # 2. Quota
        if not skip_quota:
            try:
                self.quota.check_and_increment(student_id, qtype)
            except QuotaExceededError as e:
                return SolveResult({
                    "ok": False,
                    "error": "quota_exceeded",
                    "message": str(e),
                    "student_id": student_id,
                    "question_type": qtype,
                    "queued": False,
                })

        # 3. Cache
        cached = self.quota.cache_get(question, subject)
        if cached and float(cached.get("confidence") or 0) >= self.confidence_threshold():
            thread = self._ensure_thread(student_id, subject, topic, thread_id)
            msg = self._persist_assistant(
                thread, student_id, question, qtype, subject, topic, board,
                answer=cached.get("answer_block") or "",
                how=cached.get("how_block") or "",
                why=cached.get("why_block") or "",
                confidence=float(cached.get("confidence") or 0),
                grounded=True,
                source_chunk_ids=list(cached.get("source_chunk_ids") or []),
                needs_review=False,
                review_reason="",
                model_tier=TIER_CHEAP,
                cached=True,
            )
            return SolveResult({
                "ok": True,
                "cached": True,
                "thread_id": thread["id"],
                "message_id": msg["id"],
                "answer": msg["answer_block"],
                "how": msg["how_block"],
                "why": msg["why_block"],
                "confidence": msg["confidence"],
                "grounded": True,
                "source_chunk_ids": msg["source_chunk_ids"],
                "needs_review": False,
                "question_type": qtype,
                "subject": subject,
                "topic": topic,
            })

        # 4. Retrieval
        chunks = self.retrieval.retrieve(
            query=question, subject=subject, topic=topic, batch_id=batch_id, limit=5
        )
        grounded = len(chunks) > 0
        chunk_ids = [c.resource_id for c in chunks]

        # 5. Model tier routing
        tier = TIER_CHEAP if qtype == QTYPE_MCQ else TIER_PREMIUM

        # 6. Generate (+ self-verify) or degrade
        try:
            gen = self._generate(question, subject, topic, chunks, tier)
            verify = self._self_verify(question, gen["answer"], chunks, tier)
        except RateLimitError:
            thread = self._ensure_thread(student_id, subject, topic, thread_id)
            msg = self._persist_assistant(
                thread, student_id, question, qtype, subject, topic, board,
                answer="", how="", why="",
                confidence=0.0, grounded=grounded, source_chunk_ids=chunk_ids,
                needs_review=True,
                review_reason="rate_limited — will answer when quota resets",
                model_tier=tier, cached=False,
            )
            self._flag_thread(thread["id"])
            return SolveResult({
                "ok": False,
                "error": "rate_limited",
                "message": "will answer when quota resets",
                "queued": True,
                "thread_id": thread["id"],
                "message_id": msg["id"],
                "needs_review": True,
                "grounded": grounded,
                "source_chunk_ids": chunk_ids,
            })
        except OfflineError:
            thread = self._ensure_thread(student_id, subject, topic, thread_id)
            msg = self._persist_assistant(
                thread, student_id, question, qtype, subject, topic, board,
                answer="", how="", why="",
                confidence=0.0, grounded=grounded, source_chunk_ids=chunk_ids,
                needs_review=True,
                review_reason="offline — AI unavailable until connectivity returns",
                model_tier=tier, cached=False,
            )
            self._flag_thread(thread["id"])
            return SolveResult({
                "ok": False,
                "error": "offline",
                "message": "AI unavailable until connectivity returns",
                "queued": True,
                "thread_id": thread["id"],
                "message_id": msg["id"],
                "needs_review": True,
                "grounded": grounded,
                "source_chunk_ids": chunk_ids,
            })

        # 7. Confidence + grounding gate
        confidence = self._score_confidence(gen, verify, grounded)
        needs_review = False
        review_reason = ""
        if not grounded:
            needs_review = True
            review_reason = "ungrounded — no vault sources matched"
        elif not verify["match"]:
            needs_review = True
            review_reason = "self-verification mismatch"
            # Prefer uncertainty over silent choice
            gen["answer"] = gen.get("answer") or ""
            if "uncertain" not in (gen["answer"] or "").lower():
                gen["answer"] = (
                    (gen["answer"] + "\n\n[Uncertain: verification pass disagreed.]").strip()
                )
        elif confidence < self.confidence_threshold():
            needs_review = True
            review_reason = f"low confidence ({confidence:.2f})"

        thread = self._ensure_thread(student_id, subject, topic, thread_id)
        msg = self._persist_assistant(
            thread, student_id, question, qtype, subject, topic, board,
            answer=gen.get("answer") or "",
            how=gen.get("how") or "",
            why=gen.get("why") or "",
            confidence=confidence,
            grounded=grounded,
            source_chunk_ids=chunk_ids,
            needs_review=needs_review,
            review_reason=review_reason,
            model_tier=tier,
            cached=False,
        )
        if needs_review:
            self._flag_thread(thread["id"])

        # Cache only high-confidence grounded answers
        if grounded and not needs_review and confidence >= self.confidence_threshold():
            self.quota.cache_put(
                question, subject,
                gen.get("answer") or "", gen.get("how") or "", gen.get("why") or "",
                confidence, chunk_ids,
            )

        return SolveResult({
            "ok": True,
            "cached": False,
            "thread_id": thread["id"],
            "message_id": msg["id"],
            "answer": msg["answer_block"],
            "how": msg["how_block"],
            "why": msg["why_block"],
            "confidence": confidence,
            "grounded": grounded,
            "source_chunk_ids": chunk_ids,
            "needs_review": needs_review,
            "review_reason": review_reason,
            "question_type": qtype,
            "subject": subject,
            "topic": topic,
            "verification_match": verify["match"],
        })

    # ── Internals ─────────────────────────────────────────────────────

    def _classify(
        self,
        question: str,
        subject: str,
        topic: str,
        board: str,
        question_type: Optional[str],
    ) -> Dict[str, str]:
        if question_type and subject and topic:
            return {
                "question_type": question_type if question_type in (QTYPE_MCQ, QTYPE_WRITTEN, "cq") else QTYPE_WRITTEN,
                "subject": subject,
                "topic": topic,
                "board": board or "general",
            }
        try:
            resp = self.llm.complete(
                LLMRequest(
                    prompt=f"Classify this question:\n{question}",
                    system="classify",
                    tier=TIER_CHEAP,
                )
            )
            parsed = parse_classification(resp.text)
            if subject:
                parsed["subject"] = subject
            if topic:
                parsed["topic"] = topic
            if board:
                parsed["board"] = board
            if question_type:
                parsed["question_type"] = question_type
            return parsed
        except (RateLimitError, OfflineError):
            return {
                "question_type": question_type or QTYPE_WRITTEN,
                "subject": subject or "general",
                "topic": topic or "general",
                "board": board or "general",
            }

    def _generate(
        self,
        question: str,
        subject: str,
        topic: str,
        chunks: List[RetrievalChunk],
        tier: str,
    ) -> Dict[str, str]:
        context = "\n\n".join(
            f"[{c.resource_id}] {c.title}: {c.excerpt}" for c in chunks
        ) or "(no grounded sources)"
        system = (
            "You are CohortOS Solve. Use only the provided source chunks. "
            "Output exactly three blocks: ANSWER:, HOW:, WHY:. "
            "Cite source ids when possible. If sources are insufficient, say so."
        )
        prompt = (
            f"Subject: {subject}\nTopic: {topic}\n"
            f"Sources:\n{context}\n\nQuestion: {question}"
        )
        resp = self.llm.complete(LLMRequest(prompt=prompt, system=system, tier=tier))
        return parse_answer_blocks(resp.text)

    def _self_verify(
        self,
        question: str,
        first_answer: str,
        chunks: List[RetrievalChunk],
        tier: str,
    ) -> Dict[str, Any]:
        context = "\n".join(f"- {c.excerpt}" for c in chunks) or "(none)"
        system = (
            "verification: Re-derive the answer independently from sources. "
            "Output ANSWER: HOW: WHY: only."
        )
        prompt = (
            f"Question: {question}\nSources:\n{context}\n"
            f"First-pass answer was: {first_answer}\n"
            f"Re-derive independently."
        )
        resp = self.llm.complete(LLMRequest(prompt=prompt, system=system, tier=tier))
        second = parse_answer_blocks(resp.text)
        # Simple match: normalized answer overlap
        a1 = (first_answer or "").lower().strip()
        a2 = (second.get("answer") or "").lower().strip()
        match = bool(a1 and a2 and (a1 in a2 or a2 in a1 or a1[:40] == a2[:40]))
        # Mock special marker
        if "__MISMATCH__" in question:
            match = False
        return {"match": match, "second": second}

    def _score_confidence(
        self, gen: Dict[str, str], verify: Dict[str, Any], grounded: bool
    ) -> float:
        score = 0.5
        if grounded:
            score += 0.25
        if verify.get("match"):
            score += 0.2
        if gen.get("answer") and gen.get("how"):
            score += 0.1
        if "uncertain" in (gen.get("answer") or "").lower():
            score -= 0.3
        return max(0.0, min(1.0, round(score, 3)))

    def _ensure_thread(
        self, student_id: str, subject: str, topic: str, thread_id: Optional[str]
    ) -> Dict[str, Any]:
        if thread_id:
            existing = self.data_layer.get("ai_threads", uuid.UUID(thread_id))
            if existing:
                return existing
        return self.get_or_create_thread(student_id, subject, topic)

    def _flag_thread(self, thread_id: str) -> None:
        self.data_layer.update(
            "ai_threads",
            uuid.UUID(thread_id),
            {"flagged_for_teacher": True, "updated_at": _utcnow()},
        )

    def _persist_assistant(
        self,
        thread: Dict[str, Any],
        student_id: str,
        question: str,
        qtype: str,
        subject: str,
        topic: str,
        board: str,
        answer: str,
        how: str,
        why: str,
        confidence: float,
        grounded: bool,
        source_chunk_ids: List[str],
        needs_review: bool,
        review_reason: str,
        model_tier: str,
        cached: bool,
    ) -> Dict[str, Any]:
        # student message
        student_msg = AIMessage(
            tenant_id=str(self.tenant_context.tenant_id),
            thread_id=thread["id"],
            student_id=student_id,
            role="student",
            content=question,
            question_type=qtype,
            subject=subject,
            topic=topic,
            board=board,
        )
        self.data_layer.create("ai_messages", student_msg.to_dict())

        assistant = AIMessage(
            tenant_id=str(self.tenant_context.tenant_id),
            thread_id=thread["id"],
            student_id=student_id,
            role="assistant",
            content=answer,
            question_type=qtype,
            subject=subject,
            topic=topic,
            board=board,
            answer_block=answer,
            how_block=how,
            why_block=why,
            confidence=confidence,
            grounded=grounded,
            source_chunk_ids=source_chunk_ids,
            needs_review=needs_review,
            review_reason=review_reason,
            model_tier=model_tier,
            cached=cached,
        )
        rid = self.data_layer.create("ai_messages", assistant.to_dict())
        stored = self.data_layer.get("ai_messages", rid) or assistant.to_dict()

        # update thread counters
        count = int(thread.get("message_count") or 0) + 2
        self.data_layer.update(
            "ai_threads",
            uuid.UUID(thread["id"]),
            {
                "message_count": count,
                "last_message_at": _utcnow(),
                "subject": subject or thread.get("subject"),
                "topic": topic or thread.get("topic"),
                "updated_at": _utcnow(),
            },
        )
        return stored
