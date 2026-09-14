"""
Admission & batch models for CohortOS Portion 2 (SPEC Module 1).

Covers: students/admissions, batches, batch templates, join codes,
roll encoding metadata, and migration audit records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import secrets
import string


# Day bitmask (LOCKED): Sat=1, Sun=2, Mon=4, Tue=8, Wed=16, Thu=32, Fri=64
DAY_BITS = {
    'sat': 1,
    'sun': 2,
    'mon': 4,
    'tue': 8,
    'wed': 16,
    'thu': 32,
    'fri': 64,
}
DAY_ORDER = ['sat', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri']
DAY_LABELS = {
    'sat': 'Sat', 'sun': 'Sun', 'mon': 'Mon', 'tue': 'Tue',
    'wed': 'Wed', 'thu': 'Thu', 'fri': 'Fri',
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def days_to_bitmask(days: List[str]) -> int:
    """Convert day name list to 3-digit bitmask integer (1–127)."""
    mask = 0
    for d in days:
        key = d.strip().lower()[:3]
        if key not in DAY_BITS:
            raise ValueError(f"Invalid day: {d}. Expected one of {list(DAY_BITS.keys())}")
        mask |= DAY_BITS[key]
    if mask < 1 or mask > 127:
        raise ValueError(f"Day bitmask out of range: {mask}")
    return mask


def bitmask_to_days(mask: int) -> List[str]:
    """Expand bitmask to ordered day keys."""
    if mask < 1 or mask > 127:
        raise ValueError(f"Day bitmask out of range: {mask}")
    return [d for d in DAY_ORDER if mask & DAY_BITS[d]]


def format_batch_display_name(days: List[str], hour: int) -> str:
    """Auto-generated display name, e.g. 'Sat,Mon,Wed 14:00'."""
    labels = [DAY_LABELS[d] for d in days if d in DAY_LABELS]
    return f"{','.join(labels)} {hour:02d}:00"


@dataclass
class Batch:
    """Configured batch slot for a centre."""
    id: Optional[str] = None
    tenant_id: str = ''
    name: str = ''                          # display name (auto or override)
    days: List[str] = field(default_factory=list)  # e.g. ['sat','mon','wed']
    hour: int = 14                          # 24-hour, 0–23
    day_bitmask: int = 0
    name_override: bool = False             # True if staff set name manually
    template_id: Optional[str] = None
    is_active: bool = True
    extra_sessions: List[Dict[str, Any]] = field(default_factory=list)
    # extra_sessions: [{day, hour, expires_on}]
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.days and not self.day_bitmask:
            self.day_bitmask = days_to_bitmask(self.days)
        elif self.day_bitmask and not self.days:
            self.days = bitmask_to_days(self.day_bitmask)
        if not self.name_override and not self.name and self.days:
            self.name = format_batch_display_name(self.days, self.hour)
        if not (0 <= self.hour <= 23):
            raise ValueError(f"hour must be 0–23, got {self.hour}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'days': list(self.days),
            'hour': self.hour,
            'day_bitmask': self.day_bitmask,
            'name_override': self.name_override,
            'template_id': self.template_id,
            'is_active': self.is_active,
            'extra_sessions': list(self.extra_sessions),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Batch':
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            name=data.get('name', ''),
            days=list(data.get('days') or []),
            hour=int(data.get('hour', 14)),
            day_bitmask=int(data.get('day_bitmask') or 0),
            name_override=bool(data.get('name_override', False)),
            template_id=data.get('template_id'),
            is_active=bool(data.get('is_active', True)),
            extra_sessions=list(data.get('extra_sessions') or []),
            created_at=data.get('created_at', _utcnow()),
            updated_at=data.get('updated_at', _utcnow()),
        )


@dataclass
class BatchTemplate:
    """Reusable batch/exam/messaging template per coaching type."""
    id: Optional[str] = None
    tenant_id: str = ''
    name: str = ''
    coaching_type: str = 'hsc'  # medical, hsc, english, skill, custom
    default_days: List[str] = field(default_factory=list)
    default_hour: int = 14
    exam_structure: Dict[str, Any] = field(default_factory=dict)
    messaging_templates: Dict[str, str] = field(default_factory=dict)
    # AI system prompts are opaque — only CohortOS team may set/view content
    has_ai_prompt: bool = False
    ai_prompt_request_id: Optional[str] = None
    is_active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'coaching_type': self.coaching_type,
            'default_days': list(self.default_days),
            'default_hour': self.default_hour,
            'exam_structure': dict(self.exam_structure),
            'messaging_templates': dict(self.messaging_templates),
            'has_ai_prompt': self.has_ai_prompt,
            'ai_prompt_request_id': self.ai_prompt_request_id,
            'is_active': self.is_active,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BatchTemplate':
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            name=data.get('name', ''),
            coaching_type=data.get('coaching_type', 'hsc'),
            default_days=list(data.get('default_days') or []),
            default_hour=int(data.get('default_hour', 14)),
            exam_structure=dict(data.get('exam_structure') or {}),
            messaging_templates=dict(data.get('messaging_templates') or {}),
            has_ai_prompt=bool(data.get('has_ai_prompt', False)),
            ai_prompt_request_id=data.get('ai_prompt_request_id'),
            is_active=bool(data.get('is_active', True)),
            created_at=data.get('created_at', _utcnow()),
            updated_at=data.get('updated_at', _utcnow()),
        )


@dataclass
class Student:
    """Admission / student record (anchored to admission_id = id)."""
    id: Optional[str] = None
    tenant_id: str = ''
    name: str = ''
    batch_id: str = ''
    roll: str = ''
    student_phone: str = ''
    parent_phones: List[str] = field(default_factory=list)
    whatsapp: str = ''
    cohortos_account_id: Optional[str] = None  # linked later via join code
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    biometric_device_user_id: Optional[str] = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.name or not self.name.strip():
            raise ValueError("Student name is required")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'batch_id': self.batch_id,
            'roll': self.roll,
            'student_phone': self.student_phone,
            'parent_phones': list(self.parent_phones),
            'whatsapp': self.whatsapp,
            'cohortos_account_id': self.cohortos_account_id,
            'custom_fields': dict(self.custom_fields),
            'is_active': self.is_active,
            'biometric_device_user_id': self.biometric_device_user_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Student':
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            name=data.get('name', ''),
            batch_id=data.get('batch_id', ''),
            roll=data.get('roll', ''),
            student_phone=data.get('student_phone', ''),
            parent_phones=list(data.get('parent_phones') or []),
            whatsapp=data.get('whatsapp', ''),
            cohortos_account_id=data.get('cohortos_account_id'),
            custom_fields=dict(data.get('custom_fields') or {}),
            is_active=bool(data.get('is_active', True)),
            biometric_device_user_id=data.get('biometric_device_user_id'),
            created_at=data.get('created_at', _utcnow()),
            updated_at=data.get('updated_at', _utcnow()),
        )


@dataclass
class JoinCode:
    """Per-admission join code (QR + alphanumeric). SPEC Module 8 [LOCKED]."""
    id: Optional[str] = None
    tenant_id: str = ''
    admission_id: str = ''          # = student.id
    code: str = ''                  # short alphanumeric
    is_used: bool = False
    expires_at: str = ''            # default 30 days from creation (SPEC_v3)
    used_at: Optional[str] = None
    used_by_account_id: Optional[str] = None
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.code:
            self.code = self._generate_code()

    @staticmethod
    def _generate_code(length: int = 8) -> str:
        alphabet = string.ascii_uppercase + string.digits
        # Avoid ambiguous chars
        alphabet = alphabet.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'admission_id': self.admission_id,
            'code': self.code,
            'is_used': self.is_used,
            'expires_at': self.expires_at,
            'used_at': self.used_at,
            'used_by_account_id': self.used_by_account_id,
            'created_at': self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JoinCode':
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            admission_id=data.get('admission_id', ''),
            code=data.get('code', ''),
            is_used=bool(data.get('is_used', False)),
            expires_at=data.get('expires_at', ''),
            used_at=data.get('used_at'),
            used_by_account_id=data.get('used_by_account_id'),
            created_at=data.get('created_at', _utcnow()),
        )


@dataclass
class DuplicateMatch:
    """Concrete conflicting record surfaced before save."""
    student_id: str
    name: str
    roll: str
    student_phone: str
    reason: str  # e.g. "Phone number already registered to student X, roll Y"


@dataclass
class MigrationRecord:
    """Audit record for atomic roll/batch migration."""
    id: Optional[str] = None
    tenant_id: str = ''
    student_id: str = ''
    old_roll: str = ''
    new_roll: str = ''
    old_batch_id: str = ''
    new_batch_id: str = ''
    tables_migrated: List[str] = field(default_factory=list)
    records_moved: int = 0
    actor_id: Optional[str] = None
    status: str = 'completed'  # completed | failed | rolled_back
    error_message: Optional[str] = None
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'student_id': self.student_id,
            'old_roll': self.old_roll,
            'new_roll': self.new_roll,
            'old_batch_id': self.old_batch_id,
            'new_batch_id': self.new_batch_id,
            'tables_migrated': list(self.tables_migrated),
            'records_moved': self.records_moved,
            'actor_id': self.actor_id,
            'status': self.status,
            'error_message': self.error_message,
            'created_at': self.created_at,
        }
