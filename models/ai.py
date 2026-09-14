"""
AI domain models — CohortOS Solve + Teach (SPEC Module 9).

Threads are keyed to student_id (admission id) per SPEC §8 history ownership.
All generated Teach items require teacher approval before student-facing use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import hashlib
import json


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Question / item types ─────────────────────────────────────────────

QTYPE_MCQ = "mcq"
QTYPE_WRITTEN = "written"
QTYPE_CQ = "cq"
QTYPE_FOLLOWUP = "followup"
VALID_QTYPES = frozenset({QTYPE_MCQ, QTYPE_WRITTEN, QTYPE_CQ, QTYPE_FOLLOWUP})

TIER_CHEAP = "cheap"
TIER_PREMIUM = "premium"

# Review / publication states
STATUS_DRAFT = "draft"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_EDITED = "edited"
VALID_ITEM_STATUSES = frozenset({
    STATUS_DRAFT, STATUS_NEEDS_REVIEW, STATUS_APPROVED, STATUS_REJECTED, STATUS_EDITED
})

# Confidence
DEFAULT_CONFIDENCE_THRESHOLD = 0.65

# Quota defaults (per day)
DEFAULT_DAILY_MCQ_CAP = 30
DEFAULT_DAILY_WRITTEN_CAP = 10


@dataclass
class RetrievalChunk:
    """One grounded source fragment from the Vault (or vetted primary set)."""
    resource_id: str
    title: str = ""
    topic: str = ""
    subject: str = ""
    excerpt: str = ""
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "title": self.title,
            "topic": self.topic,
            "subject": self.subject,
            "excerpt": self.excerpt,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetrievalChunk":
        return cls(
            resource_id=str(data.get("resource_id") or ""),
            title=data.get("title") or "",
            topic=data.get("topic") or "",
            subject=data.get("subject") or "",
            excerpt=data.get("excerpt") or "",
            score=float(data.get("score") or 0),
        )


@dataclass
class AIMessage:
    """One turn in a Solve conversation thread."""
    id: Optional[str] = None
    tenant_id: str = ""
    thread_id: str = ""
    student_id: str = ""
    role: str = "student"  # student | assistant | teacher
    content: str = ""
    question_type: str = QTYPE_WRITTEN
    subject: str = ""
    topic: str = ""
    board: str = ""
    answer_block: str = ""
    how_block: str = ""
    why_block: str = ""
    confidence: float = 0.0
    grounded: bool = False
    source_chunk_ids: List[str] = field(default_factory=list)
    needs_review: bool = False
    review_reason: str = ""
    model_tier: str = TIER_CHEAP
    cached: bool = False
    teacher_annotation: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "thread_id": self.thread_id,
            "student_id": self.student_id,
            "role": self.role,
            "content": self.content,
            "question_type": self.question_type,
            "subject": self.subject,
            "topic": self.topic,
            "board": self.board,
            "answer_block": self.answer_block,
            "how_block": self.how_block,
            "why_block": self.why_block,
            "confidence": self.confidence,
            "grounded": self.grounded,
            "source_chunk_ids": list(self.source_chunk_ids),
            "needs_review": self.needs_review,
            "review_reason": self.review_reason,
            "model_tier": self.model_tier,
            "cached": self.cached,
            "teacher_annotation": self.teacher_annotation,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AIMessage":
        return cls(
            id=data.get("id"),
            tenant_id=data.get("tenant_id") or "",
            thread_id=data.get("thread_id") or "",
            student_id=data.get("student_id") or "",
            role=data.get("role") or "student",
            content=data.get("content") or "",
            question_type=data.get("question_type") or QTYPE_WRITTEN,
            subject=data.get("subject") or "",
            topic=data.get("topic") or "",
            board=data.get("board") or "",
            answer_block=data.get("answer_block") or "",
            how_block=data.get("how_block") or "",
            why_block=data.get("why_block") or "",
            confidence=float(data.get("confidence") or 0),
            grounded=bool(data.get("grounded")),
            source_chunk_ids=list(data.get("source_chunk_ids") or []),
            needs_review=bool(data.get("needs_review")),
            review_reason=data.get("review_reason") or "",
            model_tier=data.get("model_tier") or TIER_CHEAP,
            cached=bool(data.get("cached")),
            teacher_annotation=data.get("teacher_annotation") or "",
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
        )


@dataclass
class AIThread:
    """Conversation thread owned by an admission (student_id)."""
    id: Optional[str] = None
    tenant_id: str = ""
    student_id: str = ""
    subject: str = ""
    topic: str = ""
    title: str = ""
    message_count: int = 0
    last_message_at: str = ""
    flagged_for_teacher: bool = False
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "student_id": self.student_id,
            "subject": self.subject,
            "topic": self.topic,
            "title": self.title,
            "message_count": self.message_count,
            "last_message_at": self.last_message_at,
            "flagged_for_teacher": self.flagged_for_teacher,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AIThread":
        return cls(
            id=data.get("id"),
            tenant_id=data.get("tenant_id") or "",
            student_id=data.get("student_id") or "",
            subject=data.get("subject") or "",
            topic=data.get("topic") or "",
            title=data.get("title") or "",
            message_count=int(data.get("message_count") or 0),
            last_message_at=data.get("last_message_at") or "",
            flagged_for_teacher=bool(data.get("flagged_for_teacher")),
            is_active=bool(data.get("is_active", True)),
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
        )


@dataclass
class AIGeneratedItem:
    """
    Teach-generated item (MCQ / written / solution / analytics suggestion).
    Never student-visible until status == approved.
    """
    id: Optional[str] = None
    tenant_id: str = ""
    item_type: str = QTYPE_MCQ  # mcq | written | cq | solution | analytics
    subject: str = ""
    topic: str = ""
    content: Dict[str, Any] = field(default_factory=dict)
    status: str = STATUS_DRAFT
    confidence: float = 0.0
    grounded: bool = False
    source_chunk_ids: List[str] = field(default_factory=list)
    review_reason: str = ""
    version: int = 1
    created_by: str = ""  # staff id or 'system'
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejected_by: Optional[str] = None
    rejected_at: Optional[str] = None
    reject_reason: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)
    impact_score: float = 0.0  # for analytics ranking
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "item_type": self.item_type,
            "subject": self.subject,
            "topic": self.topic,
            "content": dict(self.content),
            "status": self.status,
            "confidence": self.confidence,
            "grounded": self.grounded,
            "source_chunk_ids": list(self.source_chunk_ids),
            "review_reason": self.review_reason,
            "version": self.version,
            "created_by": self.created_by,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "rejected_by": self.rejected_by,
            "rejected_at": self.rejected_at,
            "reject_reason": self.reject_reason,
            "history": list(self.history),
            "impact_score": self.impact_score,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AIGeneratedItem":
        return cls(
            id=data.get("id"),
            tenant_id=data.get("tenant_id") or "",
            item_type=data.get("item_type") or QTYPE_MCQ,
            subject=data.get("subject") or "",
            topic=data.get("topic") or "",
            content=dict(data.get("content") or {}),
            status=data.get("status") or STATUS_DRAFT,
            confidence=float(data.get("confidence") or 0),
            grounded=bool(data.get("grounded")),
            source_chunk_ids=list(data.get("source_chunk_ids") or []),
            review_reason=data.get("review_reason") or "",
            version=int(data.get("version") or 1),
            created_by=data.get("created_by") or "",
            approved_by=data.get("approved_by"),
            approved_at=data.get("approved_at"),
            rejected_by=data.get("rejected_by"),
            rejected_at=data.get("rejected_at"),
            reject_reason=data.get("reject_reason") or "",
            history=list(data.get("history") or []),
            impact_score=float(data.get("impact_score") or 0),
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
        )


@dataclass
class TeacherStyleProfile:
    """Few-shot style lock for Teach [BULLET]."""
    id: Optional[str] = None
    tenant_id: str = ""
    subject: str = ""
    version: int = 1
    style_notes: str = ""
    terminology: List[str] = field(default_factory=list)
    sign_conventions: str = ""
    difficulty: str = "medium"
    few_shot_examples: List[Dict[str, str]] = field(default_factory=list)
    preferred_language: str = "en"  # en | bn | banglish
    is_active: bool = True
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "subject": self.subject,
            "version": self.version,
            "style_notes": self.style_notes,
            "terminology": list(self.terminology),
            "sign_conventions": self.sign_conventions,
            "difficulty": self.difficulty,
            "few_shot_examples": list(self.few_shot_examples),
            "preferred_language": self.preferred_language,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TeacherStyleProfile":
        return cls(
            id=data.get("id"),
            tenant_id=data.get("tenant_id") or "",
            subject=data.get("subject") or "",
            version=int(data.get("version") or 1),
            style_notes=data.get("style_notes") or "",
            terminology=list(data.get("terminology") or []),
            sign_conventions=data.get("sign_conventions") or "",
            difficulty=data.get("difficulty") or "medium",
            few_shot_examples=list(data.get("few_shot_examples") or []),
            preferred_language=data.get("preferred_language") or "en",
            is_active=bool(data.get("is_active", True)),
            created_by=data.get("created_by") or "",
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
        )


@dataclass
class QueryCacheEntry:
    """Semantic-ish cache of common Solve answers [BULLET]."""
    id: Optional[str] = None
    tenant_id: str = ""
    query_hash: str = ""
    query_normalized: str = ""
    subject: str = ""
    answer_block: str = ""
    how_block: str = ""
    why_block: str = ""
    confidence: float = 0.0
    source_chunk_ids: List[str] = field(default_factory=list)
    hit_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "query_hash": self.query_hash,
            "query_normalized": self.query_normalized,
            "subject": self.subject,
            "answer_block": self.answer_block,
            "how_block": self.how_block,
            "why_block": self.why_block,
            "confidence": self.confidence,
            "source_chunk_ids": list(self.source_chunk_ids),
            "hit_count": self.hit_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueryCacheEntry":
        return cls(
            id=data.get("id"),
            tenant_id=data.get("tenant_id") or "",
            query_hash=data.get("query_hash") or "",
            query_normalized=data.get("query_normalized") or "",
            subject=data.get("subject") or "",
            answer_block=data.get("answer_block") or "",
            how_block=data.get("how_block") or "",
            why_block=data.get("why_block") or "",
            confidence=float(data.get("confidence") or 0),
            source_chunk_ids=list(data.get("source_chunk_ids") or []),
            hit_count=int(data.get("hit_count") or 0),
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
        )


def normalize_query(text: str) -> str:
    """Simple normalize for cache keying."""
    return " ".join(text.lower().split())


def query_hash(text: str, subject: str = "") -> str:
    n = normalize_query(text) + "|" + (subject or "").lower()
    return hashlib.sha256(n.encode("utf-8")).hexdigest()[:32]


@dataclass
class StudentQuotaUsage:
    """Per-student daily query counters [FLEX][BULLET]."""
    id: Optional[str] = None
    tenant_id: str = ""
    student_id: str = ""
    date: str = ""  # YYYY-MM-DD
    mcq_count: int = 0
    written_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "student_id": self.student_id,
            "date": self.date,
            "mcq_count": self.mcq_count,
            "written_count": self.written_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StudentQuotaUsage":
        return cls(
            id=data.get("id"),
            tenant_id=data.get("tenant_id") or "",
            student_id=data.get("student_id") or "",
            date=data.get("date") or "",
            mcq_count=int(data.get("mcq_count") or 0),
            written_count=int(data.get("written_count") or 0),
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
        )
