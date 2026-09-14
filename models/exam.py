"""
Exam / Results models for CohortOS Portion 5 (SPEC Module 4).

- Flexible exam templates (default main-exam structure + custom)
- Exam instances (scheduled or ad-hoc)
- Permanent student results (never lost on roll/batch change)
- Section-level scores for MCQ / written / CQ analytics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import json


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# Section types used in templates and results
SECTION_MCQ = 'mcq'
SECTION_WRITTEN = 'written'       # physics-maths style
SECTION_CQ = 'cq'
SECTION_OPEN_BOOK = 'open_book'
SECTION_CUSTOM = 'custom'

VALID_SECTION_TYPES = frozenset({
    SECTION_MCQ, SECTION_WRITTEN, SECTION_CQ, SECTION_OPEN_BOOK, SECTION_CUSTOM,
})

# Exam instance status
EXAM_DRAFT = 'draft'
EXAM_SCHEDULED = 'scheduled'
EXAM_IN_PROGRESS = 'in_progress'
EXAM_COMPLETED = 'completed'
EXAM_CANCELLED = 'cancelled'

VALID_EXAM_STATUSES = frozenset({
    EXAM_DRAFT, EXAM_SCHEDULED, EXAM_IN_PROGRESS, EXAM_COMPLETED, EXAM_CANCELLED,
})


def default_main_exam_sections() -> List[Dict[str, Any]]:
    """
    SPEC default “main exam” structure (origin client physics coaching):
    1. 15 MCQs, 9 minutes — immediate result
    2. 6 physics-maths questions, 60 marks, 18 minutes
    3. 1 CQ, 10 marks
    """
    return [
        {
            'key': 'mcq',
            'name': 'MCQ',
            'section_type': SECTION_MCQ,
            'max_marks': 15,          # 1 mark each by default
            'question_count': 15,
            'duration_minutes': 9,
            'weight': 1.0,
            'immediate_result': True,
        },
        {
            'key': 'written',
            'name': 'Physics Maths',
            'section_type': SECTION_WRITTEN,
            'max_marks': 60,
            'question_count': 6,
            'duration_minutes': 18,
            'weight': 1.0,
            'immediate_result': False,
        },
        {
            'key': 'cq',
            'name': 'CQ',
            'section_type': SECTION_CQ,
            'max_marks': 10,
            'question_count': 1,
            'duration_minutes': 0,    # not time-boxed separately in origin workflow
            'weight': 1.0,
            'immediate_result': False,
        },
    ]


@dataclass
class ExamTemplate:
    """
    Reusable exam structure. Centres start with the default main-exam template
    and may create any number of custom templates [FLEX].
    """
    id: Optional[str] = None
    tenant_id: str = ''
    name: str = ''
    description: str = ''
    is_default: bool = False
    is_open_book: bool = False          # low-priority optional type
    subject: str = ''                   # optional tag
    sections: List[Dict[str, Any]] = field(default_factory=list)
    is_active: bool = True
    origin_id: str = ''
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.origin_id:
            self.origin_id = f"local-{uuid.uuid4().hex[:8]}"
        if not self.sections:
            if self.is_open_book:
                self.sections = [{
                    'key': 'open_book',
                    'name': 'Open Book',
                    'section_type': SECTION_OPEN_BOOK,
                    'max_marks': 50,
                    'question_count': 0,
                    'duration_minutes': 0,
                    'weight': 1.0,
                    'immediate_result': False,
                }]
            else:
                self.sections = default_main_exam_sections()
        # Validate section types
        for s in self.sections:
            st = s.get('section_type', SECTION_CUSTOM)
            if st not in VALID_SECTION_TYPES:
                raise ValueError(f"Invalid section_type: {st}")

    def total_max_marks(self) -> float:
        return sum(float(s.get('max_marks', 0) or 0) for s in self.sections)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'description': self.description,
            'is_default': self.is_default,
            'is_open_book': self.is_open_book,
            'subject': self.subject,
            'sections': self.sections,
            'is_active': self.is_active,
            'origin_id': self.origin_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'total_max_marks': self.total_max_marks(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExamTemplate':
        sections = data.get('sections') or []
        if isinstance(sections, str):
            sections = json.loads(sections)
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            name=data.get('name', ''),
            description=data.get('description', ''),
            is_default=bool(data.get('is_default', False)),
            is_open_book=bool(data.get('is_open_book', False)),
            subject=data.get('subject', ''),
            sections=sections,
            is_active=bool(data.get('is_active', True)),
            origin_id=data.get('origin_id', ''),
            created_at=data.get('created_at', _utcnow()),
            updated_at=data.get('updated_at', _utcnow()),
        )


@dataclass
class Exam:
    """
    A concrete exam sitting (scheduled or ad-hoc).
    Linked to an optional template; ad-hoc exams may have free-form sections.
    """
    id: Optional[str] = None
    tenant_id: str = ''
    template_id: Optional[str] = None
    batch_id: str = ''
    name: str = ''
    exam_date: str = ''                 # YYYY-MM-DD
    chapter_or_topic: str = ''          # for analytics / heatmaps
    subject: str = ''
    status: str = EXAM_DRAFT
    sections: List[Dict[str, Any]] = field(default_factory=list)
    is_ad_hoc: bool = False
    notes: str = ''
    origin_id: str = ''
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.origin_id:
            self.origin_id = f"local-{uuid.uuid4().hex[:8]}"
        if self.status not in VALID_EXAM_STATUSES:
            raise ValueError(f"Invalid exam status: {self.status}")
        if not self.sections and not self.is_ad_hoc:
            self.sections = default_main_exam_sections()

    def total_max_marks(self) -> float:
        return sum(float(s.get('max_marks', 0) or 0) for s in self.sections)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'template_id': self.template_id,
            'batch_id': self.batch_id,
            'name': self.name,
            'exam_date': self.exam_date,
            'chapter_or_topic': self.chapter_or_topic,
            'subject': self.subject,
            'status': self.status,
            'sections': self.sections,
            'is_ad_hoc': self.is_ad_hoc,
            'notes': self.notes,
            'origin_id': self.origin_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'total_max_marks': self.total_max_marks(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Exam':
        sections = data.get('sections') or []
        if isinstance(sections, str):
            sections = json.loads(sections)
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            template_id=data.get('template_id'),
            batch_id=data.get('batch_id', ''),
            name=data.get('name', ''),
            exam_date=data.get('exam_date', ''),
            chapter_or_topic=data.get('chapter_or_topic', ''),
            subject=data.get('subject', ''),
            status=data.get('status', EXAM_DRAFT),
            sections=sections,
            is_ad_hoc=bool(data.get('is_ad_hoc', False)),
            notes=data.get('notes', ''),
            origin_id=data.get('origin_id', ''),
            created_at=data.get('created_at', _utcnow()),
            updated_at=data.get('updated_at', _utcnow()),
        )


@dataclass
class ExamResult:
    """
    One student's permanent result for one exam.
    Section scores stored as list of {key, marks_obtained, max_marks, notes}.
    History is never deleted; migration rewrites roll/batch_id only.
    """
    id: Optional[str] = None
    tenant_id: str = ''
    exam_id: str = ''
    student_id: str = ''
    batch_id: str = ''
    roll: str = ''
    exam_date: str = ''
    chapter_or_topic: str = ''
    section_scores: List[Dict[str, Any]] = field(default_factory=list)
    total_obtained: float = 0.0
    total_max: float = 0.0
    percentage: float = 0.0
    is_absent: bool = False
    entered_by: Optional[str] = None
    notes: str = ''
    origin_id: str = ''
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.origin_id:
            self.origin_id = f"local-{uuid.uuid4().hex[:8]}"
        if not self.student_id:
            raise ValueError("student_id is required")
        if not self.exam_id and not self.is_absent:
            # allow absent without exam_id only in edge tests; production always sets it
            pass
        self._recompute_totals()

    def _recompute_totals(self) -> None:
        if self.is_absent:
            self.total_obtained = 0.0
            self.percentage = 0.0
            return
        obtained = 0.0
        maximum = 0.0
        for s in self.section_scores:
            obtained += float(s.get('marks_obtained', 0) or 0)
            maximum += float(s.get('max_marks', 0) or 0)
        self.total_obtained = round(obtained, 2)
        self.total_max = round(maximum, 2) if maximum else self.total_max
        if self.total_max > 0:
            self.percentage = round(100.0 * self.total_obtained / self.total_max, 2)
        else:
            self.percentage = 0.0

    def to_dict(self) -> Dict[str, Any]:
        self._recompute_totals()
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'exam_id': self.exam_id,
            'student_id': self.student_id,
            'batch_id': self.batch_id,
            'roll': self.roll,
            'exam_date': self.exam_date,
            'chapter_or_topic': self.chapter_or_topic,
            'section_scores': self.section_scores,
            'total_obtained': self.total_obtained,
            'total_max': self.total_max,
            'percentage': self.percentage,
            'is_absent': self.is_absent,
            'entered_by': self.entered_by,
            'notes': self.notes,
            'origin_id': self.origin_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExamResult':
        scores = data.get('section_scores') or []
        if isinstance(scores, str):
            scores = json.loads(scores)
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            exam_id=data.get('exam_id', ''),
            student_id=data.get('student_id', ''),
            batch_id=data.get('batch_id', ''),
            roll=data.get('roll', ''),
            exam_date=data.get('exam_date', ''),
            chapter_or_topic=data.get('chapter_or_topic', ''),
            section_scores=scores,
            total_obtained=float(data.get('total_obtained', 0) or 0),
            total_max=float(data.get('total_max', 0) or 0),
            percentage=float(data.get('percentage', 0) or 0),
            is_absent=bool(data.get('is_absent', False)),
            entered_by=data.get('entered_by'),
            notes=data.get('notes', ''),
            origin_id=data.get('origin_id', ''),
            created_at=data.get('created_at', _utcnow()),
            updated_at=data.get('updated_at', _utcnow()),
        )
