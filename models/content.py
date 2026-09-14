"""
Content / CohortOS Vault models — Portion 6 (SPEC Module 5).

Resources, access rules, anti-leak policy, chunked upload state,
offline cache markers, minimal live-session support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import json


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# Resource types
TYPE_PDF = 'pdf'
TYPE_SHEET = 'sheet'
TYPE_VIDEO_YOUTUBE = 'video_youtube'
TYPE_VIDEO_MP4 = 'video_mp4'
TYPE_IMAGE = 'image'
TYPE_LIVE_RECORDING = 'live_recording'
TYPE_LINK = 'link'

VALID_RESOURCE_TYPES = frozenset({
    TYPE_PDF, TYPE_SHEET, TYPE_VIDEO_YOUTUBE, TYPE_VIDEO_MP4,
    TYPE_IMAGE, TYPE_LIVE_RECORDING, TYPE_LINK,
})

# Access rule operators
OP_AND = 'AND'
OP_OR = 'OR'
VALID_OPS = frozenset({OP_AND, OP_OR})

# Rule kinds
RULE_MIN_ATTENDANCE = 'min_attendance_pct'
RULE_SAT_LAST_EXAM = 'sat_last_exam'
RULE_PAID_UP = 'paid_up'
RULE_EXPIRES_ON = 'expires_on'
RULE_ALWAYS_ALLOW = 'always_allow'
RULE_ALWAYS_DENY = 'always_deny'

VALID_RULE_KINDS = frozenset({
    RULE_MIN_ATTENDANCE, RULE_SAT_LAST_EXAM, RULE_PAID_UP,
    RULE_EXPIRES_ON, RULE_ALWAYS_ALLOW, RULE_ALWAYS_DENY,
})

# Anti-leak protection levels
PROTECT_OWNER_ONLY = 'owner_only'       # centre default [LOCKED]
PROTECT_RELAXED = 'relaxed'             # teacher/assistant relaxed
PROTECT_OPEN = 'open'                   # fully open (still audit-logged)

VALID_PROTECTION = frozenset({PROTECT_OWNER_ONLY, PROTECT_RELAXED, PROTECT_OPEN})

# Live session status
LIVE_SCHEDULED = 'scheduled'
LIVE_LIVE = 'live'
LIVE_ENDED = 'ended'
LIVE_CANCELLED = 'cancelled'
VALID_LIVE_STATUS = frozenset({LIVE_SCHEDULED, LIVE_LIVE, LIVE_ENDED, LIVE_CANCELLED})


@dataclass
class AccessRule:
    """
    Single condition in a resource's access ruleset.
    Composable via the parent ruleset operator (AND/OR).
    """
    kind: str
    value: Any = None                   # e.g. 75 for min_attendance_pct, '2026-12-31' for expires
    batch_id: Optional[str] = None      # optional per-batch scope

    def __post_init__(self):
        if self.kind not in VALID_RULE_KINDS:
            raise ValueError(f"Invalid rule kind: {self.kind}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'kind': self.kind,
            'value': self.value,
            'batch_id': self.batch_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AccessRule':
        return cls(
            kind=data['kind'],
            value=data.get('value'),
            batch_id=data.get('batch_id'),
        )


@dataclass
class AccessRuleset:
    """Composable set of AccessRules with AND/OR operator [BULLET]."""
    operator: str = OP_AND
    rules: List[AccessRule] = field(default_factory=list)

    def __post_init__(self):
        if self.operator not in VALID_OPS:
            raise ValueError(f"Invalid operator: {self.operator}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'operator': self.operator,
            'rules': [r.to_dict() for r in self.rules],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AccessRuleset':
        if not data:
            return cls()
        rules = [AccessRule.from_dict(r) for r in (data.get('rules') or [])]
        return cls(operator=data.get('operator', OP_AND), rules=rules)

    @classmethod
    def empty(cls) -> 'AccessRuleset':
        return cls(operator=OP_AND, rules=[])


@dataclass
class ContentResource:
    """
    One vault resource: PDF, video, image, etc.
    Manual entry priority; linked to topic/chapter.
    """
    id: Optional[str] = None
    tenant_id: str = ''
    title: str = ''
    description: str = ''
    resource_type: str = TYPE_PDF
    topic: str = ''                     # chapter / topic for library
    subject: str = ''
    batch_ids: List[str] = field(default_factory=list)  # empty = all batches
    # Content location
    url: str = ''                       # youtube link, external URL, or local path
    file_path: str = ''                 # local/storage path for uploaded files
    youtube_timestamps: List[Dict[str, Any]] = field(default_factory=list)  # [{label, seconds}]
    mime_type: str = ''
    file_size_bytes: int = 0
    # Chunked upload / resumable download
    total_chunks: int = 0
    uploaded_chunks: int = 0
    checksum: str = ''
    # Access
    access_rules: Dict[str, Any] = field(default_factory=dict)  # AccessRuleset.to_dict()
    # Anti-leak [LOCKED]
    protection_level: str = PROTECT_OWNER_ONLY
    watermark: bool = True
    no_download: bool = True
    session_token_required: bool = True
    protection_relaxed_by: Optional[str] = None
    protection_relaxed_at: Optional[str] = None
    # Meta
    is_active: bool = True
    created_by: Optional[str] = None
    origin_id: str = ''
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.origin_id:
            self.origin_id = f"local-{uuid.uuid4().hex[:8]}"
        if self.resource_type not in VALID_RESOURCE_TYPES:
            raise ValueError(f"Invalid resource_type: {self.resource_type}")
        if self.protection_level not in VALID_PROTECTION:
            raise ValueError(f"Invalid protection_level: {self.protection_level}")
        if not self.title:
            raise ValueError("title is required")

    @property
    def is_protection_relaxed(self) -> bool:
        return self.protection_level == PROTECT_RELAXED

    @property
    def upload_complete(self) -> bool:
        if self.total_chunks <= 0:
            return True  # non-chunked or external URL
        return self.uploaded_chunks >= self.total_chunks

    def ruleset(self) -> AccessRuleset:
        return AccessRuleset.from_dict(self.access_rules or {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'title': self.title,
            'description': self.description,
            'resource_type': self.resource_type,
            'topic': self.topic,
            'subject': self.subject,
            'batch_ids': self.batch_ids,
            'url': self.url,
            'file_path': self.file_path,
            'youtube_timestamps': self.youtube_timestamps,
            'mime_type': self.mime_type,
            'file_size_bytes': self.file_size_bytes,
            'total_chunks': self.total_chunks,
            'uploaded_chunks': self.uploaded_chunks,
            'checksum': self.checksum,
            'access_rules': self.access_rules,
            'protection_level': self.protection_level,
            'watermark': self.watermark,
            'no_download': self.no_download,
            'session_token_required': self.session_token_required,
            'protection_relaxed_by': self.protection_relaxed_by,
            'protection_relaxed_at': self.protection_relaxed_at,
            'is_protection_relaxed': self.is_protection_relaxed,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'origin_id': self.origin_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'upload_complete': self.upload_complete,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContentResource':
        batch_ids = data.get('batch_ids') or []
        if isinstance(batch_ids, str):
            batch_ids = json.loads(batch_ids)
        timestamps = data.get('youtube_timestamps') or []
        if isinstance(timestamps, str):
            timestamps = json.loads(timestamps)
        rules = data.get('access_rules') or {}
        if isinstance(rules, str):
            rules = json.loads(rules)
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            title=data.get('title', ''),
            description=data.get('description', ''),
            resource_type=data.get('resource_type', TYPE_PDF),
            topic=data.get('topic', ''),
            subject=data.get('subject', ''),
            batch_ids=batch_ids,
            url=data.get('url', ''),
            file_path=data.get('file_path', ''),
            youtube_timestamps=timestamps,
            mime_type=data.get('mime_type', ''),
            file_size_bytes=int(data.get('file_size_bytes', 0) or 0),
            total_chunks=int(data.get('total_chunks', 0) or 0),
            uploaded_chunks=int(data.get('uploaded_chunks', 0) or 0),
            checksum=data.get('checksum', ''),
            access_rules=rules,
            protection_level=data.get('protection_level', PROTECT_OWNER_ONLY),
            watermark=bool(data.get('watermark', True)),
            no_download=bool(data.get('no_download', True)),
            session_token_required=bool(data.get('session_token_required', True)),
            protection_relaxed_by=data.get('protection_relaxed_by'),
            protection_relaxed_at=data.get('protection_relaxed_at'),
            is_active=bool(data.get('is_active', True)),
            created_by=data.get('created_by'),
            origin_id=data.get('origin_id', ''),
            created_at=data.get('created_at', _utcnow()),
            updated_at=data.get('updated_at', _utcnow()),
        )


@dataclass
class OfflineCacheEntry:
    """Student pre-download marker for offline study [BULLET]."""
    id: Optional[str] = None
    tenant_id: str = ''
    student_id: str = ''
    resource_id: str = ''
    cached_at: str = field(default_factory=_utcnow)
    last_access_check: Optional[str] = None
    last_access_allowed: bool = True
    local_path: str = ''
    origin_id: str = ''
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.origin_id:
            self.origin_id = f"local-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'student_id': self.student_id,
            'resource_id': self.resource_id,
            'cached_at': self.cached_at,
            'last_access_check': self.last_access_check,
            'last_access_allowed': self.last_access_allowed,
            'local_path': self.local_path,
            'origin_id': self.origin_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OfflineCacheEntry':
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            student_id=data.get('student_id', ''),
            resource_id=data.get('resource_id', ''),
            cached_at=data.get('cached_at', _utcnow()),
            last_access_check=data.get('last_access_check'),
            last_access_allowed=bool(data.get('last_access_allowed', True)),
            local_path=data.get('local_path', ''),
            origin_id=data.get('origin_id', ''),
            created_at=data.get('created_at', _utcnow()),
            updated_at=data.get('updated_at', _utcnow()),
        )


@dataclass
class LiveSession:
    """
    Minimal online coaching session [NEW].
    Full realtime chat/WebRTC is out of band; we store session metadata,
    hand-raises, and poll payloads for offline-first continuity.
    """
    id: Optional[str] = None
    tenant_id: str = ''
    batch_id: str = ''
    title: str = ''
    status: str = LIVE_SCHEDULED
    scheduled_start: str = ''
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    host_id: Optional[str] = None
    hand_raises: List[str] = field(default_factory=list)   # student_ids
    polls: List[Dict[str, Any]] = field(default_factory=list)
    recording_resource_id: Optional[str] = None
    notes: str = ''
    origin_id: str = ''
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.origin_id:
            self.origin_id = f"local-{uuid.uuid4().hex[:8]}"
        if self.status not in VALID_LIVE_STATUS:
            raise ValueError(f"Invalid live session status: {self.status}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'batch_id': self.batch_id,
            'title': self.title,
            'status': self.status,
            'scheduled_start': self.scheduled_start,
            'started_at': self.started_at,
            'ended_at': self.ended_at,
            'host_id': self.host_id,
            'hand_raises': self.hand_raises,
            'polls': self.polls,
            'recording_resource_id': self.recording_resource_id,
            'notes': self.notes,
            'origin_id': self.origin_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LiveSession':
        hand_raises = data.get('hand_raises') or []
        if isinstance(hand_raises, str):
            hand_raises = json.loads(hand_raises)
        polls = data.get('polls') or []
        if isinstance(polls, str):
            polls = json.loads(polls)
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            batch_id=data.get('batch_id', ''),
            title=data.get('title', ''),
            status=data.get('status', LIVE_SCHEDULED),
            scheduled_start=data.get('scheduled_start', ''),
            started_at=data.get('started_at'),
            ended_at=data.get('ended_at'),
            host_id=data.get('host_id'),
            hand_raises=hand_raises,
            polls=polls,
            recording_resource_id=data.get('recording_resource_id'),
            notes=data.get('notes', ''),
            origin_id=data.get('origin_id', ''),
            created_at=data.get('created_at', _utcnow()),
            updated_at=data.get('updated_at', _utcnow()),
        )


@dataclass
class ViewerSessionToken:
    """Per-user session token for anti-leak in-app viewer [LOCKED]."""
    id: Optional[str] = None
    tenant_id: str = ''
    resource_id: str = ''
    user_id: str = ''                   # student or staff
    token: str = ''
    watermark_text: str = ''
    expires_at: str = ''
    revoked: bool = False
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.token:
            self.token = uuid.uuid4().hex

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'resource_id': self.resource_id,
            'user_id': self.user_id,
            'token': self.token,
            'watermark_text': self.watermark_text,
            'expires_at': self.expires_at,
            'revoked': self.revoked,
            'created_at': self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ViewerSessionToken':
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            resource_id=data.get('resource_id', ''),
            user_id=data.get('user_id', ''),
            token=data.get('token', ''),
            watermark_text=data.get('watermark_text', ''),
            expires_at=data.get('expires_at', ''),
            revoked=bool(data.get('revoked', False)),
            created_at=data.get('created_at', _utcnow()),
        )
