"""
Content / CohortOS Vault service — SPEC Module 5.

- Resource CRUD (PDF, video, image, sheet, live recording, link)
- Per-topic library
- Access rules engine (composable AND/OR) [BULLET]
- Anti-leak: owner_only default, teacher/assistant relax, desk blocked [LOCKED]
- Chunked upload / resumable download metadata
- Offline cache markers + access re-check [BULLET]
- Minimal live sessions (hand-raise, polls)
- AI video-suggest stub [FLEX]
- Offline-first, tenant-scoped, audit-logged, sync-ready
"""

from __future__ import annotations

from datetime import datetime, timezone, date, timedelta
from typing import Any, Dict, List, Optional, Set
import uuid
import copy

from models.base import TenantContext, DataAccessLayer
from models.content import (
    ContentResource, AccessRule, AccessRuleset, OfflineCacheEntry,
    LiveSession, ViewerSessionToken,
    TYPE_PDF, TYPE_SHEET, TYPE_VIDEO_YOUTUBE, TYPE_VIDEO_MP4,
    TYPE_IMAGE, TYPE_LIVE_RECORDING, TYPE_LINK,
    OP_AND, OP_OR,
    RULE_MIN_ATTENDANCE, RULE_SAT_LAST_EXAM, RULE_PAID_UP,
    RULE_EXPIRES_ON, RULE_ALWAYS_ALLOW, RULE_ALWAYS_DENY,
    PROTECT_OWNER_ONLY, PROTECT_RELAXED, PROTECT_OPEN,
    LIVE_SCHEDULED, LIVE_LIVE, LIVE_ENDED, LIVE_CANCELLED,
    _utcnow,
)
from services.audit_service import AuditService
from services.config_service import ConfigService


# Roles that may relax anti-leak protection
RELAX_ALLOWED_ROLES = frozenset({'owner', 'teacher', 'assistant'})
# Desk explicitly cannot touch anti-leak
RELAX_DENIED_ROLES = frozenset({'desk'})


class AccessDeniedError(Exception):
    """Raised when a student/user fails access rules or protection checks."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class ProtectionPermissionError(Exception):
    """Raised when a role attempts anti-leak actions it is not allowed to perform."""
    pass


class ContentService:
    """Offline-first content vault."""

    def __init__(
        self,
        tenant_context: TenantContext,
        data_layer: Optional[DataAccessLayer] = None,
        audit_service: Optional[AuditService] = None,
        config_service: Optional[ConfigService] = None,
        attendance_service=None,
        payment_service=None,
        exam_service=None,
        sync_engine=None,
    ):
        self.tenant_context = tenant_context
        self.data_layer = data_layer or DataAccessLayer(tenant_context)
        self.audit_service = audit_service or AuditService(tenant_context)
        self.config_service = config_service or ConfigService(tenant_context)
        self.attendance_service = attendance_service
        self.payment_service = payment_service
        self.exam_service = exam_service
        self.sync_engine = sync_engine

    # ── Resource CRUD ─────────────────────────────────────────────────

    def create_resource(
        self,
        title: str,
        resource_type: str = TYPE_PDF,
        topic: str = '',
        subject: str = '',
        description: str = '',
        url: str = '',
        file_path: str = '',
        batch_ids: Optional[List[str]] = None,
        youtube_timestamps: Optional[List[Dict[str, Any]]] = None,
        mime_type: str = '',
        file_size_bytes: int = 0,
        total_chunks: int = 0,
        access_rules: Optional[Dict[str, Any]] = None,
        protection_level: str = PROTECT_OWNER_ONLY,
        watermark: bool = True,
        no_download: bool = True,
        session_token_required: bool = True,
        actor_id: Optional[str] = None,
        actor_role: str = 'owner',
    ) -> str:
        # Desk cannot set relaxed protection on create
        if protection_level == PROTECT_RELAXED and actor_role in RELAX_DENIED_ROLES:
            raise ProtectionPermissionError(
                "Desk role cannot set or relax anti-leak protection"
            )
        res = ContentResource(
            tenant_id=str(self.tenant_context.tenant_id),
            title=title,
            description=description,
            resource_type=resource_type,
            topic=topic,
            subject=subject,
            batch_ids=batch_ids or [],
            url=url,
            file_path=file_path,
            youtube_timestamps=youtube_timestamps or [],
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            total_chunks=total_chunks,
            access_rules=access_rules or AccessRuleset.empty().to_dict(),
            protection_level=protection_level,
            watermark=watermark,
            no_download=no_download,
            session_token_required=session_token_required,
            created_by=actor_id,
        )
        rid = self.data_layer.create('content_resources', res.to_dict())
        stored = self.data_layer.get('content_resources', rid)
        self.audit_service.log_create(
            table_name='content_resources',
            record_id=rid,
            new_state=stored or res.to_dict(),
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._persist_audit()
        self._queue_sync('create', 'content_resources', str(rid), None, stored)
        return str(rid)

    def get_resource(self, resource_id: str) -> Optional[Dict[str, Any]]:
        return self.data_layer.get('content_resources', uuid.UUID(resource_id))

    def list_resources(
        self,
        topic: Optional[str] = None,
        subject: Optional[str] = None,
        resource_type: Optional[str] = None,
        batch_id: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        rows = self.data_layer.get_all('content_resources')
        if active_only:
            rows = [r for r in rows if r.get('is_active', True)]
        if topic:
            rows = [r for r in rows if r.get('topic') == topic]
        if subject:
            rows = [r for r in rows if r.get('subject') == subject]
        if resource_type:
            rows = [r for r in rows if r.get('resource_type') == resource_type]
        if batch_id:
            rows = [
                r for r in rows
                if not r.get('batch_ids') or batch_id in (r.get('batch_ids') or [])
            ]
        rows.sort(key=lambda r: (r.get('topic', ''), r.get('title', '')))
        return rows

    def update_resource(
        self,
        resource_id: str,
        actor_id: Optional[str] = None,
        actor_role: str = 'owner',
        **kwargs,
    ) -> bool:
        old = self.get_resource(resource_id)
        if not old:
            return False
        # Anti-leak fields: desk cannot change
        anti_leak_keys = {
            'protection_level', 'watermark', 'no_download', 'session_token_required',
        }
        if actor_role in RELAX_DENIED_ROLES and any(k in kwargs for k in anti_leak_keys):
            raise ProtectionPermissionError(
                "Desk role cannot modify anti-leak settings"
            )
        allowed = {
            'title', 'description', 'topic', 'subject', 'url', 'file_path',
            'batch_ids', 'youtube_timestamps', 'mime_type', 'file_size_bytes',
            'total_chunks', 'uploaded_chunks', 'checksum', 'access_rules',
            'protection_level', 'watermark', 'no_download', 'session_token_required',
            'is_active',
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        updates['updated_at'] = _utcnow()
        ok = self.data_layer.update('content_resources', uuid.UUID(resource_id), updates)
        if ok:
            new = self.get_resource(resource_id)
            self.audit_service.log_update(
                table_name='content_resources',
                record_id=uuid.UUID(resource_id),
                old_state=old,
                new_state=new or updates,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._persist_audit()
            self._queue_sync('update', 'content_resources', resource_id, old, new)
        return ok

    def deactivate_resource(self, resource_id: str, actor_id: Optional[str] = None) -> bool:
        return self.update_resource(resource_id, actor_id=actor_id, is_active=False)

    # ── Chunked upload ────────────────────────────────────────────────

    def register_chunk_progress(
        self,
        resource_id: str,
        uploaded_chunks: int,
        checksum: str = '',
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update chunk progress for resumable upload/download."""
        res = self.get_resource(resource_id)
        if not res:
            raise ValueError(f"Resource not found: {resource_id}")
        total = int(res.get('total_chunks', 0) or 0)
        if total > 0 and uploaded_chunks > total:
            raise ValueError(f"uploaded_chunks {uploaded_chunks} exceeds total_chunks {total}")
        updates = {
            'uploaded_chunks': uploaded_chunks,
            'updated_at': _utcnow(),
        }
        if checksum:
            updates['checksum'] = checksum
        self.update_resource(resource_id, actor_id=actor_id, **updates)
        out = self.get_resource(resource_id) or {}
        t = int(out.get('total_chunks', 0) or 0)
        u = int(out.get('uploaded_chunks', 0) or 0)
        out['upload_complete'] = True if t <= 0 else (u >= t)
        return out

    # ── Access rules [BULLET] ─────────────────────────────────────────

    def set_access_rules(
        self,
        resource_id: str,
        operator: str,
        rules: List[Dict[str, Any]],
        actor_id: Optional[str] = None,
    ) -> bool:
        ruleset = AccessRuleset(
            operator=operator,
            rules=[AccessRule.from_dict(r) for r in rules],
        )
        return self.update_resource(
            resource_id,
            actor_id=actor_id,
            access_rules=ruleset.to_dict(),
        )

    def evaluate_access(
        self,
        resource_id: str,
        student_id: str,
        force_recheck: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate whether student may access resource.
        Returns {allowed: bool, reasons: [str], resource_id, student_id}.
        Re-evaluates offline-cache eligibility when force_recheck=True [BULLET].
        """
        res = self.get_resource(resource_id)
        if not res or not res.get('is_active', True):
            return {
                'allowed': False,
                'reasons': ['resource_not_found_or_inactive'],
                'resource_id': resource_id,
                'student_id': student_id,
            }

        ruleset = AccessRuleset.from_dict(res.get('access_rules') or {})
        if not ruleset.rules:
            # No rules → allow (protection level still applies for viewing)
            result = {
                'allowed': True,
                'reasons': ['no_rules'],
                'resource_id': resource_id,
                'student_id': student_id,
            }
        else:
            results = [self._eval_rule(rule, student_id, res) for rule in ruleset.rules]
            if ruleset.operator == OP_AND:
                allowed = all(r[0] for r in results)
            else:
                allowed = any(r[0] for r in results)
            reasons = [r[1] for r in results if not r[0]] if not allowed else ['passed']
            result = {
                'allowed': allowed,
                'reasons': reasons,
                'resource_id': resource_id,
                'student_id': student_id,
            }

        if force_recheck:
            self._update_cache_access_flag(student_id, resource_id, result['allowed'])
        return result

    def _eval_rule(
        self,
        rule: AccessRule,
        student_id: str,
        resource: Dict[str, Any],
    ) -> tuple:
        """Return (passed: bool, reason: str)."""
        kind = rule.kind
        if kind == RULE_ALWAYS_ALLOW:
            return True, 'always_allow'
        if kind == RULE_ALWAYS_DENY:
            return False, 'always_deny'
        if kind == RULE_EXPIRES_ON:
            exp = str(rule.value or '')
            if not exp:
                return True, 'no_expiry'
            try:
                if date.today().isoformat() > exp:
                    return False, f'expired_on_{exp}'
            except Exception:
                return False, 'invalid_expiry'
            return True, 'not_expired'
        if kind == RULE_MIN_ATTENDANCE:
            pct_required = float(rule.value or 0)
            if not self.attendance_service:
                # Degrade open when dependency missing (offline resilience)
                return True, 'attendance_service_unavailable'
            try:
                today = date.today()
                # Approximate: attended days / days so far in month * 100
                attended = self.attendance_service.count_attended_days(
                    student_id, year=today.year, month=today.month
                )
                # Use day-of-month as rough denominator (configurable later)
                denom = max(today.day, 1)
                pct = 100.0 * attended / denom
                if pct < pct_required:
                    return False, f'attendance_{pct:.0f}_lt_{pct_required:.0f}'
                return True, f'attendance_ok_{pct:.0f}'
            except Exception:
                return True, 'attendance_check_error'
        if kind == RULE_PAID_UP:
            if not self.payment_service:
                return True, 'payment_service_unavailable'
            try:
                today = date.today()
                rec = self.payment_service.get_payment(student_id, today.year, today.month)
                if not rec or rec.get('status') != 'paid':
                    return False, 'not_paid_up'
                return True, 'paid_up'
            except Exception:
                return True, 'payment_check_error'
        if kind == RULE_SAT_LAST_EXAM:
            if not self.exam_service:
                return True, 'exam_service_unavailable'
            try:
                results = self.exam_service.get_student_results(student_id)
                # "last exam" = most recent completed exam for same batch if possible
                if not results:
                    return False, 'no_exam_results'
                # any non-absent result counts as sat
                sat = any(not r.get('is_absent') for r in results)
                if not sat:
                    return False, 'did_not_sit_last_exam'
                return True, 'sat_exam'
            except Exception:
                return True, 'exam_check_error'
        return False, f'unknown_rule_{kind}'

    # ── Anti-leak [BULLET][LOCKED] ────────────────────────────────────

    def relax_protection(
        self,
        resource_id: str,
        actor_id: str,
        actor_role: str,
    ) -> Dict[str, Any]:
        """
        Teacher/assistant/owner may relax protection on any resource.
        Desk cannot. Always audit-logged; resource labeled protection_relaxed.
        """
        if actor_role in RELAX_DENIED_ROLES or actor_role not in RELAX_ALLOWED_ROLES:
            raise ProtectionPermissionError(
                f"Role '{actor_role}' cannot relax anti-leak protection"
            )
        old = self.get_resource(resource_id)
        if not old:
            raise ValueError(f"Resource not found: {resource_id}")
        updates = {
            'protection_level': PROTECT_RELAXED,
            'protection_relaxed_by': actor_id,
            'protection_relaxed_at': _utcnow(),
            'watermark': False,
            'no_download': False,
            'session_token_required': False,
            'updated_at': _utcnow(),
        }
        self.data_layer.update('content_resources', uuid.UUID(resource_id), updates)
        new = self.get_resource(resource_id)
        self.audit_service.log_update(
            table_name='content_resources',
            record_id=uuid.UUID(resource_id),
            old_state=old,
            new_state=new or updates,
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._persist_audit()
        self._queue_sync('update', 'content_resources', resource_id, old, new)
        return new or {**old, **updates}

    def restore_protection(
        self,
        resource_id: str,
        actor_id: str,
        actor_role: str,
    ) -> Dict[str, Any]:
        """Restore owner_only protection (owner/teacher/assistant only)."""
        if actor_role in RELAX_DENIED_ROLES or actor_role not in RELAX_ALLOWED_ROLES:
            raise ProtectionPermissionError(
                f"Role '{actor_role}' cannot restore anti-leak protection"
            )
        return self.update_resource(
            resource_id,
            actor_id=actor_id,
            actor_role=actor_role,
            protection_level=PROTECT_OWNER_ONLY,
            watermark=True,
            no_download=True,
            session_token_required=True,
            protection_relaxed_by=None,
            protection_relaxed_at=None,
        ) and self.get_resource(resource_id) or {}

    def issue_viewer_token(
        self,
        resource_id: str,
        user_id: str,
        ttl_minutes: int = 120,
        watermark_text: str = '',
    ) -> Dict[str, Any]:
        """Issue per-user session token for in-app viewer [LOCKED]."""
        res = self.get_resource(resource_id)
        if not res:
            raise ValueError(f"Resource not found: {resource_id}")
        if not res.get('session_token_required', True) and res.get('protection_level') == PROTECT_OPEN:
            # still issue token for audit trail consistency
            pass
        expires = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
        if not watermark_text:
            watermark_text = f"{user_id}|{resource_id}|{expires[:10]}"
        tok = ViewerSessionToken(
            tenant_id=str(self.tenant_context.tenant_id),
            resource_id=resource_id,
            user_id=user_id,
            watermark_text=watermark_text,
            expires_at=expires,
        )
        rid = self.data_layer.create('viewer_session_tokens', tok.to_dict())
        stored = self.data_layer.get('viewer_session_tokens', rid)
        return stored or tok.to_dict()

    def validate_viewer_token(self, token: str, resource_id: str, user_id: str) -> bool:
        for t in self.data_layer.get_all('viewer_session_tokens'):
            if (
                t.get('token') == token
                and t.get('resource_id') == resource_id
                and t.get('user_id') == user_id
                and not t.get('revoked')
            ):
                exp = t.get('expires_at') or ''
                if exp and exp < _utcnow():
                    return False
                return True
        return False

    def revoke_viewer_token(self, token: str) -> bool:
        for t in self.data_layer.get_all('viewer_session_tokens'):
            if t.get('token') == token:
                self.data_layer.update(
                    'viewer_session_tokens',
                    uuid.UUID(t['id']),
                    {'revoked': True},
                )
                return True
        return False

    # ── Offline cache [BULLET] ────────────────────────────────────────

    def mark_for_offline(
        self,
        student_id: str,
        resource_id: str,
        local_path: str = '',
    ) -> Dict[str, Any]:
        """Student pre-downloads allowed resource for offline study."""
        access = self.evaluate_access(resource_id, student_id)
        if not access['allowed']:
            raise AccessDeniedError(
                f"Cannot cache offline: {', '.join(access['reasons'])}"
            )
        # upsert
        existing = None
        for e in self.data_layer.get_all('offline_cache_entries'):
            if e.get('student_id') == student_id and e.get('resource_id') == resource_id:
                existing = e
                break
        entry = OfflineCacheEntry(
            id=existing['id'] if existing else None,
            tenant_id=str(self.tenant_context.tenant_id),
            student_id=student_id,
            resource_id=resource_id,
            local_path=local_path,
            last_access_check=_utcnow(),
            last_access_allowed=True,
        )
        payload = entry.to_dict()
        if existing:
            payload['id'] = existing['id']
            payload['created_at'] = existing.get('created_at', payload['created_at'])
            self.data_layer.update(
                'offline_cache_entries', uuid.UUID(existing['id']), payload
            )
            return self.data_layer.get('offline_cache_entries', uuid.UUID(existing['id'])) or payload
        rid = self.data_layer.create('offline_cache_entries', payload)
        return self.data_layer.get('offline_cache_entries', rid) or payload

    def list_offline_cache(self, student_id: str) -> List[Dict[str, Any]]:
        return [
            e for e in self.data_layer.get_all('offline_cache_entries')
            if e.get('student_id') == student_id
        ]

    def recheck_offline_access(self, student_id: str) -> List[Dict[str, Any]]:
        """On reconnect: re-evaluate all cached resources [BULLET]."""
        results = []
        for e in self.list_offline_cache(student_id):
            access = self.evaluate_access(
                e['resource_id'], student_id, force_recheck=True
            )
            results.append(access)
        return results

    def _update_cache_access_flag(
        self, student_id: str, resource_id: str, allowed: bool
    ) -> None:
        for e in self.data_layer.get_all('offline_cache_entries'):
            if e.get('student_id') == student_id and e.get('resource_id') == resource_id:
                self.data_layer.update(
                    'offline_cache_entries',
                    uuid.UUID(e['id']),
                    {
                        'last_access_check': _utcnow(),
                        'last_access_allowed': allowed,
                        'updated_at': _utcnow(),
                    },
                )
                break

    # ── Live sessions [NEW] minimal ───────────────────────────────────

    def create_live_session(
        self,
        title: str,
        batch_id: str = '',
        scheduled_start: str = '',
        host_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> str:
        sess = LiveSession(
            tenant_id=str(self.tenant_context.tenant_id),
            batch_id=batch_id,
            title=title,
            scheduled_start=scheduled_start or _utcnow(),
            host_id=host_id or actor_id,
        )
        rid = self.data_layer.create('live_sessions', sess.to_dict())
        stored = self.data_layer.get('live_sessions', rid)
        self.audit_service.log_create(
            table_name='live_sessions',
            record_id=rid,
            new_state=stored or sess.to_dict(),
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._persist_audit()
        self._queue_sync('create', 'live_sessions', str(rid), None, stored)
        return str(rid)

    def get_live_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.data_layer.get('live_sessions', uuid.UUID(session_id))

    def start_live_session(self, session_id: str, actor_id: Optional[str] = None) -> bool:
        return self._update_live(session_id, {
            'status': LIVE_LIVE,
            'started_at': _utcnow(),
        }, actor_id)

    def end_live_session(
        self,
        session_id: str,
        recording_resource_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> bool:
        updates = {'status': LIVE_ENDED, 'ended_at': _utcnow()}
        if recording_resource_id:
            updates['recording_resource_id'] = recording_resource_id
        return self._update_live(session_id, updates, actor_id)

    def raise_hand(self, session_id: str, student_id: str) -> bool:
        sess = self.get_live_session(session_id)
        if not sess or sess.get('status') != LIVE_LIVE:
            return False
        hands = list(sess.get('hand_raises') or [])
        if student_id not in hands:
            hands.append(student_id)
        return self._update_live(session_id, {'hand_raises': hands}, None)

    def lower_hand(self, session_id: str, student_id: str) -> bool:
        sess = self.get_live_session(session_id)
        if not sess:
            return False
        hands = [h for h in (sess.get('hand_raises') or []) if h != student_id]
        return self._update_live(session_id, {'hand_raises': hands}, None)

    def add_poll(
        self,
        session_id: str,
        question: str,
        options: List[str],
        actor_id: Optional[str] = None,
    ) -> bool:
        sess = self.get_live_session(session_id)
        if not sess:
            return False
        polls = list(sess.get('polls') or [])
        polls.append({
            'id': str(uuid.uuid4()),
            'question': question,
            'options': options,
            'votes': {},
            'created_at': _utcnow(),
        })
        return self._update_live(session_id, {'polls': polls}, actor_id)

    def _update_live(
        self, session_id: str, updates: Dict[str, Any], actor_id: Optional[str]
    ) -> bool:
        old = self.get_live_session(session_id)
        if not old:
            return False
        updates = dict(updates)
        updates['updated_at'] = _utcnow()
        ok = self.data_layer.update('live_sessions', uuid.UUID(session_id), updates)
        if ok:
            new = self.get_live_session(session_id)
            self.audit_service.log_update(
                table_name='live_sessions',
                record_id=uuid.UUID(session_id),
                old_state=old,
                new_state=new or updates,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._persist_audit()
            self._queue_sync('update', 'live_sessions', session_id, old, new)
        return ok

    # ── AI video-suggest stub [FLEX] ──────────────────────────────────

    def suggest_videos(self, topic: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Optional low-priority helper. Returns empty list by design —
        must not consume significant build time (SPEC [FLEX]).
        """
        return []

    # ── Helpers ───────────────────────────────────────────────────────

    def _persist_audit(self) -> None:
        try:
            self.audit_service.save_logs_to_storage(self.data_layer)
        except Exception:
            pass

    def _queue_sync(self, op_type, table, record_id, old_state, new_state):
        if self.sync_engine:
            try:
                self.sync_engine.queue_operation(
                    operation_type=op_type,
                    table_name=table,
                    record_id=record_id,
                    old_state=old_state,
                    new_state=new_state,
                )
            except Exception:
                pass
