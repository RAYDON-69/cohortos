"""
Attendance & Irregularity models for CohortOS Portion 3 (SPEC Module 2).

Covers: devices, raw punches, daily attendance status, review flags,
late/absent/cross-batch/anti-proxy rules, shared irregularity threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, date, time, timedelta
from typing import Any, Dict, List, Optional, Literal
import uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# Status values for daily attendance_records
STATUS_PRESENT = 'present'
STATUS_LATE = 'late'
STATUS_ABSENT = 'absent'
STATUS_CROSS_BATCH = 'cross_batch'
STATUS_REVIEW = 'review'

VALID_STATUSES = frozenset({
    STATUS_PRESENT, STATUS_LATE, STATUS_ABSENT, STATUS_CROSS_BATCH, STATUS_REVIEW,
})

SOURCE_BIOMETRIC = 'biometric'
SOURCE_MANUAL = 'manual'
VALID_SOURCES = frozenset({SOURCE_BIOMETRIC, SOURCE_MANUAL})

# Review flag types
FLAG_ANTI_PROXY = 'anti_proxy'
FLAG_BIO_MANUAL_CONFLICT = 'bio_manual_conflict'
FLAG_IMPLAUSIBLE = 'implausible'


@dataclass
class AttendanceDevice:
    """Registered biometric device (ZKTeco or compatible)."""
    id: Optional[str] = None
    tenant_id: str = ''
    name: str = ''
    device_type: str = 'zkteco'          # zkteco | generic
    ip_address: str = ''
    port: int = 4370
    is_active: bool = True
    last_seen_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.name or not self.name.strip():
            raise ValueError("Device name is required")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'device_type': self.device_type,
            'ip_address': self.ip_address,
            'port': self.port,
            'is_active': self.is_active,
            'last_seen_at': self.last_seen_at,
            'metadata': dict(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AttendanceDevice':
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            name=data.get('name', ''),
            device_type=data.get('device_type', 'zkteco'),
            ip_address=data.get('ip_address', ''),
            port=int(data.get('port', 4370)),
            is_active=bool(data.get('is_active', True)),
            last_seen_at=data.get('last_seen_at'),
            metadata=dict(data.get('metadata') or {}),
            created_at=data.get('created_at', _utcnow()),
            updated_at=data.get('updated_at', _utcnow()),
        )


@dataclass
class PunchRecord:
    """Immutable raw punch (biometric or manual). Never silently overwritten."""
    id: Optional[str] = None
    tenant_id: str = ''
    student_id: Optional[str] = None      # resolved after linking
    device_user_id: Optional[str] = None  # device-internal ID
    device_id: Optional[str] = None
    punched_at: str = ''                  # ISO datetime
    source: str = SOURCE_BIOMETRIC
    batch_id: Optional[str] = None        # optional context when known
    origin_id: str = ''                   # client/device origin for sync
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.source not in VALID_SOURCES:
            raise ValueError(f"Invalid source: {self.source}")
        if not self.punched_at:
            raise ValueError("punched_at is required")
        if not self.origin_id:
            self.origin_id = f"local-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'student_id': self.student_id,
            'device_user_id': self.device_user_id,
            'device_id': self.device_id,
            'punched_at': self.punched_at,
            'source': self.source,
            'batch_id': self.batch_id,
            'origin_id': self.origin_id,
            'metadata': dict(self.metadata),
            'created_at': self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PunchRecord':
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            student_id=data.get('student_id'),
            device_user_id=data.get('device_user_id'),
            device_id=data.get('device_id'),
            punched_at=data.get('punched_at', ''),
            source=data.get('source', SOURCE_BIOMETRIC),
            batch_id=data.get('batch_id'),
            origin_id=data.get('origin_id', ''),
            metadata=dict(data.get('metadata') or {}),
            created_at=data.get('created_at', _utcnow()),
        )


@dataclass
class AttendanceRecord:
    """
    Derived daily status for one student on one calendar date.
    Recomputed from punches according to [LOCKED] evaluation order.
    """
    id: Optional[str] = None
    tenant_id: str = ''
    student_id: str = ''
    batch_id: str = ''                    # student's home batch
    date: str = ''                        # YYYY-MM-DD
    status: str = STATUS_ABSENT
    late_minutes: Optional[int] = None
    credited_batch_id: Optional[str] = None  # if cross_batch, the batch that was attended
    source_precedence: str = SOURCE_MANUAL   # which source drove final status
    punch_ids: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    is_reviewed: bool = False
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    notes: str = ''
    origin_id: str = ''
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {self.status}")
        if not self.student_id or not self.date:
            raise ValueError("student_id and date are required")
        if not self.origin_id:
            self.origin_id = f"local-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'student_id': self.student_id,
            'batch_id': self.batch_id,
            'date': self.date,
            'status': self.status,
            'late_minutes': self.late_minutes,
            'credited_batch_id': self.credited_batch_id,
            'source_precedence': self.source_precedence,
            'punch_ids': list(self.punch_ids),
            'flags': list(self.flags),
            'is_reviewed': self.is_reviewed,
            'reviewed_at': self.reviewed_at,
            'reviewed_by': self.reviewed_by,
            'notes': self.notes,
            'origin_id': self.origin_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AttendanceRecord':
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            student_id=data.get('student_id', ''),
            batch_id=data.get('batch_id', ''),
            date=data.get('date', ''),
            status=data.get('status', STATUS_ABSENT),
            late_minutes=data.get('late_minutes'),
            credited_batch_id=data.get('credited_batch_id'),
            source_precedence=data.get('source_precedence', SOURCE_MANUAL),
            punch_ids=list(data.get('punch_ids') or []),
            flags=list(data.get('flags') or []),
            is_reviewed=bool(data.get('is_reviewed', False)),
            reviewed_at=data.get('reviewed_at'),
            reviewed_by=data.get('reviewed_by'),
            notes=data.get('notes', ''),
            origin_id=data.get('origin_id', ''),
            created_at=data.get('created_at', _utcnow()),
            updated_at=data.get('updated_at', _utcnow()),
        )


@dataclass
class ReviewFlag:
    """Anti-proxy or bio/manual conflict requiring human review."""
    id: Optional[str] = None
    tenant_id: str = ''
    student_id: str = ''
    date: str = ''
    flag_type: str = FLAG_ANTI_PROXY
    attendance_record_id: Optional[str] = None
    punch_ids: List[str] = field(default_factory=list)
    detail: str = ''
    is_resolved: bool = False
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    resolution_notes: str = ''
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.student_id or not self.date:
            raise ValueError("student_id and date required for ReviewFlag")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'student_id': self.student_id,
            'date': self.date,
            'flag_type': self.flag_type,
            'attendance_record_id': self.attendance_record_id,
            'punch_ids': list(self.punch_ids),
            'detail': self.detail,
            'is_resolved': self.is_resolved,
            'resolved_at': self.resolved_at,
            'resolved_by': self.resolved_by,
            'resolution_notes': self.resolution_notes,
            'created_at': self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReviewFlag':
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            student_id=data.get('student_id', ''),
            date=data.get('date', ''),
            flag_type=data.get('flag_type', FLAG_ANTI_PROXY),
            attendance_record_id=data.get('attendance_record_id'),
            punch_ids=list(data.get('punch_ids') or []),
            detail=data.get('detail', ''),
            is_resolved=bool(data.get('is_resolved', False)),
            resolved_at=data.get('resolved_at'),
            resolved_by=data.get('resolved_by'),
            resolution_notes=data.get('resolution_notes', ''),
            created_at=data.get('created_at', _utcnow()),
        )


# Helpers used by the service

def parse_iso_dt(s: str) -> datetime:
    """Parse ISO datetime, accepting trailing Z or offset."""
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    return datetime.fromisoformat(s)


def date_str(d: date | datetime | str) -> str:
    if isinstance(d, str):
        return d[:10]
    if isinstance(d, datetime):
        return d.date().isoformat()
    return d.isoformat()


def weekday_key(d: date | datetime | str) -> str:
    """Return day key matching admission DAY_ORDER: sat/sun/mon/..."""
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    elif isinstance(d, datetime):
        d = d.date()
    # Python: Mon=0 ... Sun=6 → map to our keys
    mapping = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    return mapping[d.weekday()]
