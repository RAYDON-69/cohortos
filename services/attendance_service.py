"""
Attendance / Irregularity service — SPEC Module 2.

Implements:
- Biometric (ZKTeco via adapter) + manual punches
- [LOCKED] evaluation order: collect punches → anti-proxy → own/cross-batch credit
- Biometric authoritative; manual fills gaps only; conflicts → review queue
- Late threshold (global + per-batch override), default 12 min
- Cross-batch credit on own scheduled days
- Extra sessions
- Teacher absentees view
- Shared irregularity threshold (default <3 days attended / month)
- Notification integration for absence / late / late-streak (respecting threshold)
- Offline-first, tenant-scoped, audit-logged
"""

from __future__ import annotations

from datetime import datetime, date, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Set
import uuid
import copy

from models.base import TenantContext, DataAccessLayer
from models.attendance import (
    AttendanceDevice, PunchRecord, AttendanceRecord, ReviewFlag,
    STATUS_PRESENT, STATUS_LATE, STATUS_ABSENT, STATUS_CROSS_BATCH, STATUS_REVIEW,
    SOURCE_BIOMETRIC, SOURCE_MANUAL,
    FLAG_ANTI_PROXY, FLAG_BIO_MANUAL_CONFLICT, FLAG_IMPLAUSIBLE,
    parse_iso_dt, date_str, weekday_key, _utcnow,
)
from services.audit_service import AuditService
from services.config_service import ConfigService


# Defaults matching SPEC
DEFAULT_LATE_THRESHOLD_MINUTES = 12
DEFAULT_ANTI_PROXY_WINDOW_SECONDS = 90
DEFAULT_MAX_LATE_MINUTES = 90  # SPEC_v3: beyond this → absent (not late)
DEFAULT_IRREGULARITY_THRESHOLD_DAYS = 3


class AttendanceService:
    """Offline-first attendance engine."""

    def __init__(
        self,
        tenant_context: TenantContext,
        data_layer: Optional[DataAccessLayer] = None,
        audit_service: Optional[AuditService] = None,
        config_service: Optional[ConfigService] = None,
        notification_service=None,
        sync_engine=None,
    ):
        self.tenant_context = tenant_context
        self.data_layer = data_layer or DataAccessLayer(tenant_context)
        self.audit_service = audit_service or AuditService(tenant_context)
        self.config_service = config_service or ConfigService(tenant_context)
        self.notification_service = notification_service
        self.sync_engine = sync_engine

    # ── Config helpers ────────────────────────────────────────────────

    def get_late_threshold(self, batch_id: Optional[str] = None) -> int:
        """Global default or per-batch override (SPEC [FLEX])."""
        if batch_id:
            per = self.config_service.get('attendance.late_threshold_per_batch') or {}
            if isinstance(per, dict) and batch_id in per:
                return int(per[batch_id])
        return int(self.config_service.get(
            'attendance.late_threshold_minutes', DEFAULT_LATE_THRESHOLD_MINUTES
        ) or DEFAULT_LATE_THRESHOLD_MINUTES)

    def get_max_late_cutoff(self, batch_id: Optional[str] = None) -> int:
        """
        SPEC_v3 [HARDENED]: upper bound for Late status.
        Beyond this, a punch no longer counts as attendance for the session
        (raw punch logged; day stays Absent unless cross-batch credit applies).
        Default = min(batch duration if known, 90 minutes).
        """
        if batch_id:
            per = self.config_service.get('attendance.max_late_per_batch') or {}
            if isinstance(per, dict) and batch_id in per:
                return int(per[batch_id])
        configured = self.config_service.get('attendance.max_late_minutes', None)
        if configured is not None:
            return int(configured)
        # Prefer batch duration if available, else 90
        if batch_id:
            batch = self.data_layer.get('batches', __import__('uuid').UUID(batch_id)) if batch_id else None
            if batch and batch.get('duration_minutes'):
                return min(int(batch['duration_minutes']), DEFAULT_MAX_LATE_MINUTES)
        return DEFAULT_MAX_LATE_MINUTES

    def get_anti_proxy_window(self) -> int:
        return int(self.config_service.get(
            'attendance.anti_proxy_window_seconds', DEFAULT_ANTI_PROXY_WINDOW_SECONDS
        ) or DEFAULT_ANTI_PROXY_WINDOW_SECONDS)

    def get_irregularity_threshold(self, batch_id: Optional[str] = None) -> int:
        """
        Shared threshold with Payment module (SPEC [LOCKED]).
        Students with fewer attended days than this in the month are 'irregular'
        and stop receiving automated absence/payment messages.
        """
        if batch_id:
            per = self.config_service.get('attendance.irregularity_threshold_per_batch') or {}
            if isinstance(per, dict) and batch_id in per:
                return int(per[batch_id])
        return int(self.config_service.get(
            'attendance.irregularity_threshold_days', DEFAULT_IRREGULARITY_THRESHOLD_DAYS
        ) or DEFAULT_IRREGULARITY_THRESHOLD_DAYS)

    def set_late_threshold(self, minutes: int, batch_id: Optional[str] = None) -> None:
        if batch_id:
            per = dict(self.config_service.get('attendance.late_threshold_per_batch') or {})
            per[batch_id] = minutes
            self.config_service.set('attendance.late_threshold_per_batch', per)
        else:
            self.config_service.set('attendance.late_threshold_minutes', minutes)

    def set_irregularity_threshold(self, days: int, batch_id: Optional[str] = None) -> None:
        if batch_id:
            per = dict(self.config_service.get('attendance.irregularity_threshold_per_batch') or {})
            per[batch_id] = days
            self.config_service.set('attendance.irregularity_threshold_per_batch', per)
        else:
            self.config_service.set('attendance.irregularity_threshold_days', days)

    # ── Device management ─────────────────────────────────────────────

    def register_device(
        self,
        name: str,
        ip_address: str = '',
        port: int = 4370,
        device_type: str = 'zkteco',
        actor_id: Optional[str] = None,
    ) -> str:
        device = AttendanceDevice(
            tenant_id=str(self.tenant_context.tenant_id),
            name=name,
            ip_address=ip_address,
            port=port,
            device_type=device_type,
        )
        rid = self.data_layer.create('attendance_devices', device.to_dict())
        stored = self.data_layer.get('attendance_devices', rid)
        self.audit_service.log_create(
            table_name='attendance_devices',
            record_id=rid,
            new_state=stored or device.to_dict(),
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._queue_sync('create', 'attendance_devices', str(rid), None, stored)
        return str(rid)

    def deactivate_device(self, device_id: str, actor_id: Optional[str] = None) -> bool:
        """Disable device — attendance falls back to manual grid only."""
        old = self.data_layer.get('attendance_devices', uuid.UUID(device_id))
        if not old:
            return False
        ok = self.data_layer.update(
            'attendance_devices', uuid.UUID(device_id),
            {'is_active': False, 'updated_at': _utcnow()},
        )
        if ok:
            new = self.data_layer.get('attendance_devices', uuid.UUID(device_id))
            self.audit_service.log_update(
                table_name='attendance_devices',
                record_id=uuid.UUID(device_id),
                old_state=old,
                new_state=new,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._queue_sync('update', 'attendance_devices', device_id, old, new)
        return ok

    def list_devices(self, active_only: bool = True) -> List[Dict[str, Any]]:

        devices = self.data_layer.get_all('attendance_devices')
        if active_only:
            devices = [d for d in devices if d.get('is_active', True)]
        return devices

    def link_device_user(
        self,
        student_id: str,
        device_user_id: str,
        actor_id: Optional[str] = None,
    ) -> bool:
        """Manually link a student's biometric device internal user ID (SPEC)."""
        student = self.data_layer.get('students', uuid.UUID(student_id))
        if not student:
            return False
        old = dict(student)
        ok = self.data_layer.update(
            'students', uuid.UUID(student_id),
            {'biometric_device_user_id': str(device_user_id), 'updated_at': _utcnow()},
        )
        if ok:
            new = self.data_layer.get('students', uuid.UUID(student_id))
            self.audit_service.log_update(
                table_name='students',
                record_id=uuid.UUID(student_id),
                old_state=old,
                new_state=new,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._queue_sync('update', 'students', student_id, old, new)
            # Back-fill any unmatched punches that used this device_user_id
            self._resolve_orphan_punches(student_id, str(device_user_id))
        return ok

    def _resolve_orphan_punches(self, student_id: str, device_user_id: str) -> int:
        """Attach student_id to punches that only had device_user_id."""
        count = 0
        for p in self.data_layer.get_all('punch_records'):
            if p.get('device_user_id') == device_user_id and not p.get('student_id'):
                self.data_layer.update(
                    'punch_records', uuid.UUID(p['id']),
                    {'student_id': student_id},
                )
                count += 1
        return count

    # ── Punch ingestion ───────────────────────────────────────────────

    def ingest_punch(
        self,
        punched_at: str,
        student_id: Optional[str] = None,
        device_user_id: Optional[str] = None,
        device_id: Optional[str] = None,
        source: str = SOURCE_BIOMETRIC,
        batch_id: Optional[str] = None,
        origin_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        actor_id: Optional[str] = None,
        auto_evaluate: bool = True,
    ) -> str:
        """
        Record a raw punch. Works offline.
        If only device_user_id given, resolve student_id via link table.
        """
        if not student_id and device_user_id:
            student_id = self._lookup_student_by_device_user(device_user_id)

        punch = PunchRecord(
            tenant_id=str(self.tenant_context.tenant_id),
            student_id=student_id,
            device_user_id=device_user_id,
            device_id=device_id,
            punched_at=punched_at,
            source=source,
            batch_id=batch_id,
            origin_id=origin_id or f"local-{uuid.uuid4().hex[:8]}",
            metadata=metadata or {},
        )
        rid = self.data_layer.create('punch_records', punch.to_dict())
        stored = self.data_layer.get('punch_records', rid)
        self.audit_service.log_create(
            table_name='punch_records',
            record_id=rid,
            new_state=stored or punch.to_dict(),
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._queue_sync('create', 'punch_records', str(rid), None, stored)

        if auto_evaluate and student_id:
            d = date_str(punched_at)
            self.evaluate_student_day(student_id, d, actor_id=actor_id)

        return str(rid)

    def _lookup_student_by_device_user(self, device_user_id: str) -> Optional[str]:
        for s in self.data_layer.get_all('students'):
            if s.get('biometric_device_user_id') == str(device_user_id) and s.get('is_active', True):
                return s['id']
        return None

    def ingest_biometric_batch(
        self,
        punches: List[Dict[str, Any]],
        device_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> List[str]:
        """Bulk ingest from device pull (or adapter). Returns punch ids."""
        ids = []
        dates_to_eval: Set[Tuple[str, str]] = set()
        for p in punches:
            pid = self.ingest_punch(
                punched_at=p['punched_at'],
                student_id=p.get('student_id'),
                device_user_id=p.get('device_user_id'),
                device_id=device_id or p.get('device_id'),
                source=SOURCE_BIOMETRIC,
                batch_id=p.get('batch_id'),
                origin_id=p.get('origin_id'),
                metadata=p.get('metadata'),
                actor_id=actor_id,
                auto_evaluate=False,
            )
            ids.append(pid)
            sid = p.get('student_id') or self._lookup_student_by_device_user(
                str(p.get('device_user_id') or '')
            )
            if sid:
                dates_to_eval.add((sid, date_str(p['punched_at'])))
        for sid, d in dates_to_eval:
            self.evaluate_student_day(sid, d, actor_id=actor_id)
        return ids

    # ── Manual attendance (Google-Sheets style) ───────────────────────

    def mark_manual(
        self,
        student_id: str,
        on_date: str,
        status_or_time: str,
        batch_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        notes: str = '',
    ) -> str:
        """
        Manual single mark.
        status_or_time: 'present' | 'late' | 'absent' | ISO time string (implies present/late).
        Never silently overwrites an existing biometric-derived record.
        """
        on_date = date_str(on_date)
        student = self.data_layer.get('students', uuid.UUID(student_id))
        if not student:
            raise ValueError(f"Student {student_id} not found")
        home_batch = batch_id or student.get('batch_id')

        # If biometric already drove a non-absent status, manual cannot silently
        # overwrite — return existing record (SPEC [LOCKED] precedence).
        existing = self._get_attendance_record(student_id, on_date)
        if (existing
                and existing.get('source_precedence') == SOURCE_BIOMETRIC
                and existing.get('status') not in (STATUS_ABSENT, STATUS_REVIEW)
                and status_or_time in (STATUS_PRESENT, STATUS_LATE, STATUS_ABSENT, STATUS_CROSS_BATCH)):
            # Only create review if forced status disagrees
            if status_or_time != existing['status'] and status_or_time != STATUS_ABSENT:
                return self.evaluate_student_day(
                    student_id, on_date, actor_id=actor_id,
                    forced_manual_status=status_or_time, notes=notes,
                )
            return existing['id']

        # Create a manual punch if a time is supplied
        punch_id = None
        if status_or_time not in (STATUS_PRESENT, STATUS_LATE, STATUS_ABSENT, STATUS_CROSS_BATCH):
            # Treat as time
            try:
                t = parse_iso_dt(status_or_time) if 'T' in status_or_time else None
                if t is None:
                    # HH:MM on that date
                    hh, mm = map(int, status_or_time.split(':')[:2])
                    punched = f"{on_date}T{hh:02d}:{mm:02d}:00+00:00"
                else:
                    punched = status_or_time
                punch_id = self.ingest_punch(
                    punched_at=punched,
                    student_id=student_id,
                    source=SOURCE_MANUAL,
                    batch_id=home_batch,
                    actor_id=actor_id,
                    auto_evaluate=False,
                    metadata={'notes': notes} if notes else None,
                )
            except Exception as e:
                raise ValueError(f"Invalid time for manual mark: {status_or_time}") from e
        else:
            # Explicit status — still create a synthetic punch at batch start for auditability
            # only when marking present/late (absent needs no punch)
            if status_or_time in (STATUS_PRESENT, STATUS_LATE):
                batch = self.data_layer.get('batches', uuid.UUID(home_batch)) if home_batch else None
                hour = int(batch.get('hour', 14)) if batch else 14
                punched = f"{on_date}T{hour:02d}:00:00+00:00"
                if status_or_time == STATUS_LATE:
                    thresh = self.get_late_threshold(home_batch)
                    punched = f"{on_date}T{hour:02d}:{thresh+1:02d}:00+00:00"
                punch_id = self.ingest_punch(
                    punched_at=punched,
                    student_id=student_id,
                    source=SOURCE_MANUAL,
                    batch_id=home_batch,
                    actor_id=actor_id,
                    auto_evaluate=False,
                    metadata={'explicit_status': status_or_time, 'notes': notes},
                )

        return self.evaluate_student_day(
            student_id, on_date, actor_id=actor_id,
            forced_manual_status=status_or_time if status_or_time in VALID_STATUSES_FOR_FORCE else None,
            notes=notes,
        )

    def bulk_mark(
        self,
        batch_id: str,
        on_date: str,
        marks: Dict[str, str],
        actor_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Google-Sheets style bulk mark for a batch on a date.
        marks: {student_id: status_or_time}
        Returns {student_id: attendance_record_id}
        Transactional per student; overall continues on individual errors.
        """
        on_date = date_str(on_date)
        results = {}
        for sid, val in marks.items():
            try:
                rid = self.mark_manual(
                    student_id=sid,
                    on_date=on_date,
                    status_or_time=val,
                    batch_id=batch_id,
                    actor_id=actor_id,
                )
                results[sid] = rid
            except Exception as e:
                results[sid] = f"ERROR: {e}"
        return results

    # ── Core evaluation ([LOCKED] order) ──────────────────────────────

    def evaluate_student_day(
        self,
        student_id: str,
        on_date: str,
        actor_id: Optional[str] = None,
        forced_manual_status: Optional[str] = None,
        notes: str = '',
    ) -> str:
        """
        Recompute daily status for one student on one date.
        Returns attendance_record id.
        """
        on_date = date_str(on_date)
        student = self.data_layer.get('students', uuid.UUID(student_id))
        if not student:
            raise ValueError(f"Student {student_id} not found")
        home_batch_id = student.get('batch_id') or ''
        home_batch = self.data_layer.get('batches', uuid.UUID(home_batch_id)) if home_batch_id else None

        # 1. Collect all punches for this student on this date
        punches = self._punches_for_student_date(student_id, on_date)
        # Also include device_user_id matches not yet linked
        if student.get('biometric_device_user_id'):
            for p in self.data_layer.get_all('punch_records'):
                if (p.get('device_user_id') == student['biometric_device_user_id']
                        and date_str(p.get('punched_at', '')) == on_date
                        and p.get('id') not in {x['id'] for x in punches}):
                    if not p.get('student_id'):
                        self.data_layer.update(
                            'punch_records', uuid.UUID(p['id']),
                            {'student_id': student_id},
                        )
                        p = self.data_layer.get('punch_records', uuid.UUID(p['id'])) or p
                    punches.append(p)

        flags: List[str] = []
        surviving = list(punches)

        # 2. Anti-proxy check across all punches
        anti_proxy_hits = self._detect_anti_proxy(surviving)
        if anti_proxy_hits:
            flags.append(FLAG_ANTI_PROXY)
            # Do not discard punches; flag the day for review
            self._create_review_flag(
                student_id=student_id,
                on_date=on_date,
                flag_type=FLAG_ANTI_PROXY,
                punch_ids=[p['id'] for p in anti_proxy_hits],
                detail=f"Implausible multi-punch window detected ({len(anti_proxy_hits)} punches)",
                actor_id=actor_id,
            )

        # 3. Determine credit from surviving punches
        bio_punches = [p for p in surviving if p.get('source') == SOURCE_BIOMETRIC]
        man_punches = [p for p in surviving if p.get('source') == SOURCE_MANUAL]

        bio_result = self._classify_punches(
            bio_punches, student, home_batch, on_date
        ) if bio_punches else None
        man_result = self._classify_punches(
            man_punches, student, home_batch, on_date
        ) if man_punches else None

        # Honor explicit_status metadata on manual punches (teacher forced mark).
        # Classification can return ABSENT on non-scheduled days; explicit mark must stick.
        if man_punches and (not man_result or man_result.get('status') == STATUS_ABSENT):
            for p in man_punches:
                meta = p.get('metadata') or {}
                if isinstance(meta, str):
                    try:
                        import json
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                explicit = (meta.get('explicit_status') or '').lower()
                if explicit in VALID_STATUSES_FOR_FORCE and explicit != STATUS_ABSENT:
                    man_result = {
                        'status': explicit,
                        'late_minutes': None,
                        'credited_batch_id': student.get('batch_id'),
                    }
                    break

        # 4. Precedence: biometric authoritative
        final_status = STATUS_ABSENT
        late_minutes = None
        credited_batch_id = None
        source_precedence = SOURCE_MANUAL
        punch_ids = [p['id'] for p in surviving]

        if bio_result and bio_result['status'] != STATUS_ABSENT:
            final_status = bio_result['status']
            late_minutes = bio_result.get('late_minutes')
            credited_batch_id = bio_result.get('credited_batch_id')
            source_precedence = SOURCE_BIOMETRIC
        elif man_result and man_result['status'] != STATUS_ABSENT:
            final_status = man_result['status']
            late_minutes = man_result.get('late_minutes')
            credited_batch_id = man_result.get('credited_batch_id')
            source_precedence = SOURCE_MANUAL
        elif forced_manual_status and forced_manual_status != STATUS_ABSENT:
            # Explicit manual absent/present without punch classification success
            final_status = forced_manual_status
            source_precedence = SOURCE_MANUAL
        elif forced_manual_status == STATUS_ABSENT and not bio_result:
            final_status = STATUS_ABSENT
            source_precedence = SOURCE_MANUAL

        # 5. Conflict: bio says one thing, manual says another (and both non-absent)
        if (bio_result and man_result
                and bio_result['status'] != STATUS_ABSENT
                and man_result['status'] != STATUS_ABSENT
                and bio_result['status'] != man_result['status']):
            flags.append(FLAG_BIO_MANUAL_CONFLICT)
            final_status = STATUS_REVIEW
            self._create_review_flag(
                student_id=student_id,
                on_date=on_date,
                flag_type=FLAG_BIO_MANUAL_CONFLICT,
                punch_ids=punch_ids,
                detail=(
                    f"Biometric={bio_result['status']} vs Manual={man_result['status']}; "
                    "routed to review (no silent overwrite)"
                ),
                actor_id=actor_id,
            )

        if FLAG_ANTI_PROXY in flags and final_status != STATUS_REVIEW:
            # Anti-proxy always elevates to review when present
            final_status = STATUS_REVIEW

        # Persist / upsert attendance_record
        existing = self._get_attendance_record(student_id, on_date)
        record = AttendanceRecord(
            id=existing['id'] if existing else None,
            tenant_id=str(self.tenant_context.tenant_id),
            student_id=student_id,
            batch_id=home_batch_id,
            date=on_date,
            status=final_status,
            late_minutes=late_minutes,
            credited_batch_id=credited_batch_id,
            source_precedence=source_precedence,
            punch_ids=punch_ids,
            flags=flags,
            notes=notes or (existing.get('notes', '') if existing else ''),
            origin_id=f"local-{uuid.uuid4().hex[:8]}",
        )

        if existing:
            old = dict(existing)
            # Never let a manual write clobber biometric-derived status unless reviewed
            if (old.get('source_precedence') == SOURCE_BIOMETRIC
                    and source_precedence == SOURCE_MANUAL
                    and old.get('status') != STATUS_ABSENT
                    and final_status != STATUS_REVIEW
                    and FLAG_BIO_MANUAL_CONFLICT not in flags):
                # Keep biometric result; only attach new punch_ids / notes
                record.status = old['status']
                record.late_minutes = old.get('late_minutes')
                record.credited_batch_id = old.get('credited_batch_id')
                record.source_precedence = SOURCE_BIOMETRIC
                record.flags = list(set(old.get('flags', []) + flags))

            updates = record.to_dict()
            updates['updated_at'] = _utcnow()
            self.data_layer.update('attendance_records', uuid.UUID(existing['id']), updates)
            new = self.data_layer.get('attendance_records', uuid.UUID(existing['id']))
            self.audit_service.log_update(
                table_name='attendance_records',
                record_id=uuid.UUID(existing['id']),
                old_state=old,
                new_state=new,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._queue_sync('update', 'attendance_records', existing['id'], old, new)
            return existing['id']
        else:
            rid = self.data_layer.create('attendance_records', record.to_dict())
            stored = self.data_layer.get('attendance_records', rid)
            self.audit_service.log_create(
                table_name='attendance_records',
                record_id=rid,
                new_state=stored or record.to_dict(),
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._queue_sync('create', 'attendance_records', str(rid), None, stored)
            return str(rid)

    def _punches_for_student_date(self, student_id: str, on_date: str) -> List[Dict]:
        out = []
        for p in self.data_layer.get_all('punch_records'):
            if p.get('student_id') == student_id and date_str(p.get('punched_at', '')) == on_date:
                out.append(p)
        return sorted(out, key=lambda x: x.get('punched_at', ''))

    def _detect_anti_proxy(self, punches: List[Dict]) -> List[Dict]:
        """
        Same physical device, two punches within implausible window.
        Only fires when device_id is known (not None/empty) — avoids false
        positives from synthetic manual punches that share no device.
        """
        window = self.get_anti_proxy_window()
        by_device: Dict[str, List[Dict]] = {}
        for p in punches:
            did = p.get('device_id')
            if not did:
                continue  # no physical device → skip anti-proxy grouping
            by_device.setdefault(str(did), []).append(p)
        hits = []
        for did, plist in by_device.items():
            if len(plist) < 2:
                continue
            sorted_p = sorted(plist, key=lambda x: x.get('punched_at', ''))
            for i in range(1, len(sorted_p)):
                try:
                    t0 = parse_iso_dt(sorted_p[i - 1]['punched_at'])
                    t1 = parse_iso_dt(sorted_p[i]['punched_at'])
                    delta = abs((t1 - t0).total_seconds())
                    if 0 < delta < window:
                        hits.extend([sorted_p[i - 1], sorted_p[i]])
                except Exception:
                    continue
        seen = set()
        unique = []
        for h in hits:
            if h['id'] not in seen:
                seen.add(h['id'])
                unique.append(h)
        return unique

    def _classify_punches(
        self,
        punches: List[Dict],
        student: Dict,
        home_batch: Optional[Dict],
        on_date: str,
    ) -> Dict[str, Any]:
        """
        From a set of punches (already filtered by source), decide status.
        Returns dict with status, late_minutes, credited_batch_id.
        """
        if not punches:
            return {'status': STATUS_ABSENT}

        day_key = weekday_key(on_date)
        home_batch_id = student.get('batch_id') or ''

        # Is this a scheduled day for the student?
        is_scheduled = False
        if home_batch:
            days = [str(d).strip().lower()[:3] for d in (home_batch.get('days') or [])]
            if day_key in days:
                is_scheduled = True
            # extra sessions still active
            for es in home_batch.get('extra_sessions') or []:
                if es.get('day') == day_key and es.get('expires_on', '9999') >= on_date:
                    is_scheduled = True
                    break

        if not is_scheduled:
            # Not a class day for this student → no attendance obligation
            # (still record punches but do not mark absent)
            return {'status': STATUS_ABSENT}  # treated as N/A by callers if needed

        # Build candidate session windows for this weekday
        sessions = self._sessions_on_day(day_key, on_date)

        # Pick the session whose start is closest to the punch time.
        # This correctly yields cross_batch when the student attended another slot
        # rather than being "very late" to their own.
        best = None
        best_dist = None
        for p in punches:
            try:
                pt = parse_iso_dt(p['punched_at'])
            except Exception:
                continue
            for sess in sessions:
                start = datetime.combine(
                    date.fromisoformat(on_date),
                    time(sess['hour'], 0),
                    tzinfo=timezone.utc,
                )
                threshold = self.get_late_threshold(sess['batch_id'])
                max_late = self.get_max_late_cutoff(sess['batch_id'])
                late_deadline = start + timedelta(minutes=threshold)
                max_late_deadline = start + timedelta(minutes=max_late)
                # Window: from start-30min to max-late cutoff (SPEC_v3)
                window_start = start - timedelta(minutes=30)
                window_end = max_late_deadline
                if not (window_start <= pt <= window_end):
                    continue

                dist = abs((pt - start).total_seconds())
                is_own = sess['batch_id'] == home_batch_id
                if pt <= late_deadline:
                    status = STATUS_PRESENT if is_own else STATUS_CROSS_BATCH
                    late_min = None
                else:
                    # Within max-late window → Late; beyond already filtered out
                    status = STATUS_LATE if is_own else STATUS_CROSS_BATCH
                    late_min = int((pt - start).total_seconds() // 60)

                candidate = {
                    'status': status,
                    'late_minutes': late_min,
                    'credited_batch_id': sess['batch_id'],
                    'is_own': is_own,
                    'dist': dist,
                }
                if best is None or dist < best_dist:
                    best = candidate
                    best_dist = dist
                elif dist == best_dist and is_own and not best.get('is_own'):
                    # Tie-break: prefer own batch
                    best = candidate
                    best_dist = dist

        if best:
            return {
                'status': best['status'],
                'late_minutes': best.get('late_minutes'),
                'credited_batch_id': best.get('credited_batch_id'),
            }
        return {'status': STATUS_ABSENT}

    def _sessions_on_day(self, day_key: str, on_date: str) -> List[Dict]:
        """All active batch sessions (own + others) running on this weekday."""
        sessions = []
        for b in self.data_layer.get_all('batches'):
            if not b.get('is_active', True):
                continue
            days = b.get('days') or []
            if day_key in days:
                sessions.append({
                    'batch_id': b['id'],
                    'hour': int(b.get('hour', 14)),
                    'name': b.get('name', ''),
                })
            for es in b.get('extra_sessions') or []:
                if es.get('day') == day_key and es.get('expires_on', '9999') >= on_date:
                    sessions.append({
                        'batch_id': b['id'],
                        'hour': int(es.get('hour', 14)),
                        'name': f"{b.get('name')} (extra)",
                    })
        return sessions

    def _get_attendance_record(self, student_id: str, on_date: str) -> Optional[Dict]:
        for r in self.data_layer.get_all('attendance_records'):
            if r.get('student_id') == student_id and r.get('date') == on_date:
                return r
        return None

    def _create_review_flag(
        self,
        student_id: str,
        on_date: str,
        flag_type: str,
        punch_ids: List[str],
        detail: str,
        actor_id: Optional[str] = None,
    ) -> str:
        # Avoid duplicate open flags of same type for same student/date
        for f in self.data_layer.get_all('review_flags'):
            if (f.get('student_id') == student_id
                    and f.get('date') == on_date
                    and f.get('flag_type') == flag_type
                    and not f.get('is_resolved')):
                return f['id']
        flag = ReviewFlag(
            tenant_id=str(self.tenant_context.tenant_id),
            student_id=student_id,
            date=on_date,
            flag_type=flag_type,
            punch_ids=punch_ids,
            detail=detail,
        )
        rid = self.data_layer.create('review_flags', flag.to_dict())
        self.audit_service.log_create(
            table_name='review_flags',
            record_id=rid,
            new_state=flag.to_dict(),
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        return str(rid)

    # ── Teacher views ─────────────────────────────────────────────────

    def get_attendance(
        self,
        student_id: str,
        on_date: str,
    ) -> Optional[Dict[str, Any]]:
        return self._get_attendance_record(student_id, date_str(on_date))

    def get_batch_attendance(
        self,
        batch_id: str,
        on_date: str,
    ) -> List[Dict[str, Any]]:
        """All students of the batch with their status for the date."""
        on_date = date_str(on_date)
        students = [
            s for s in self.data_layer.get_all('students')
            if s.get('batch_id') == batch_id and s.get('is_active', True)
        ]
        result = []
        for s in students:
            rec = self._get_attendance_record(s['id'], on_date)
            if not rec:
                # Ensure evaluated (may be absent)
                self.evaluate_student_day(s['id'], on_date)
                rec = self._get_attendance_record(s['id'], on_date)
            result.append({
                'student_id': s['id'],
                'name': s.get('name'),
                'roll': s.get('roll'),
                'status': rec.get('status') if rec else STATUS_ABSENT,
                'late_minutes': rec.get('late_minutes') if rec else None,
                'flags': rec.get('flags', []) if rec else [],
                'record': rec,
            })
        return result

    def get_absentees(
        self,
        batch_id: str,
        on_date: str,
        days_back: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Teacher daily view (SPEC [BULLET]): prior day's absentees,
        expandable to more days back.
        """
        on_date = date_str(on_date)
        base = date.fromisoformat(on_date)
        out = []
        for i in range(days_back):
            d = (base - timedelta(days=i)).isoformat()
            day_rows = self.get_batch_attendance(batch_id, d)
            absentees = [r for r in day_rows if r['status'] == STATUS_ABSENT]
            out.append({'date': d, 'absentees': absentees, 'count': len(absentees)})
        return out

    def list_open_reviews(self, limit: int = 100) -> List[Dict[str, Any]]:
        flags = [
            f for f in self.data_layer.get_all('review_flags')
            if not f.get('is_resolved')
        ]
        flags.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return flags[:limit]

    def resolve_review(
        self,
        flag_id: str,
        final_status: str,
        actor_id: Optional[str] = None,
        notes: str = '',
    ) -> bool:
        flag = self.data_layer.get('review_flags', uuid.UUID(flag_id))
        if not flag or flag.get('is_resolved'):
            return False
        # Update attendance record
        rec = self._get_attendance_record(flag['student_id'], flag['date'])
        if rec:
            old = dict(rec)
            updates = {
                'status': final_status,
                'is_reviewed': True,
                'reviewed_at': _utcnow(),
                'reviewed_by': actor_id,
                'notes': notes or rec.get('notes', ''),
                'updated_at': _utcnow(),
            }
            self.data_layer.update('attendance_records', uuid.UUID(rec['id']), updates)
            new = self.data_layer.get('attendance_records', uuid.UUID(rec['id']))
            self.audit_service.log_update(
                table_name='attendance_records',
                record_id=uuid.UUID(rec['id']),
                old_state=old,
                new_state=new,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
        # Close flag
        self.data_layer.update(
            'review_flags', uuid.UUID(flag_id),
            {
                'is_resolved': True,
                'resolved_at': _utcnow(),
                'resolved_by': actor_id,
                'resolution_notes': notes,
            },
        )
        return True

    # ── Irregularity (shared with Payment) ────────────────────────────

    def count_attended_days(
        self,
        student_id: str,
        year: int,
        month: int,
    ) -> int:
        """Number of days with present / late / cross_batch in the month."""
        prefix = f"{year:04d}-{month:02d}-"
        count = 0
        for r in self.data_layer.get_all('attendance_records'):
            if (r.get('student_id') == student_id
                    and str(r.get('date', '')).startswith(prefix)
                    and r.get('status') in (STATUS_PRESENT, STATUS_LATE, STATUS_CROSS_BATCH)):
                count += 1
        return count

    def is_irregular(
        self,
        student_id: str,
        year: int,
        month: int,
        batch_id: Optional[str] = None,
    ) -> bool:
        """True if attended days < threshold (SPEC shared rule)."""
        threshold = self.get_irregularity_threshold(batch_id)
        return self.count_attended_days(student_id, year, month) < threshold

    def list_irregular_students(
        self,
        batch_id: str,
        year: int,
        month: int,
    ) -> List[Dict[str, Any]]:
        students = [
            s for s in self.data_layer.get_all('students')
            if s.get('batch_id') == batch_id and s.get('is_active', True)
        ]
        out = []
        thresh = self.get_irregularity_threshold(batch_id)
        for s in students:
            days = self.count_attended_days(s['id'], year, month)
            if days < thresh:
                out.append({
                    'student_id': s['id'],
                    'name': s.get('name'),
                    'roll': s.get('roll'),
                    'attended_days': days,
                    'threshold': thresh,
                })
        return out

    # ── Messaging integration ─────────────────────────────────────────

    def evaluate_and_notify(
        self,
        batch_id: str,
        on_date: str,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        After a class day: evaluate all, then queue absence/late messages
        for non-irregular students. Irregular → consolidated teacher alert.
        """
        on_date = date_str(on_date)
        d = date.fromisoformat(on_date)
        rows = self.get_batch_attendance(batch_id, on_date)
        summary = {
            'date': on_date,
            'batch_id': batch_id,
            'notified_absence': [],
            'notified_late': [],
            'skipped_irregular': [],
            'teacher_alerts': [],
            'review_count': 0,
        }

        for row in rows:
            sid = row['student_id']
            status = row['status']
            if status == STATUS_REVIEW:
                summary['review_count'] += 1
                continue
            if status == STATUS_ABSENT:
                if self.is_irregular(sid, d.year, d.month, batch_id):
                    summary['skipped_irregular'].append(sid)
                    summary['teacher_alerts'].append({
                        'student_id': sid,
                        'reason': 'irregular_absent',
                        'attended_days': self.count_attended_days(sid, d.year, d.month),
                    })
                else:
                    self._queue_absence_message(sid, on_date, batch_id)
                    summary['notified_absence'].append(sid)
            elif status == STATUS_LATE:
                # Check late streak
                streak = self._late_streak(sid, on_date)
                if streak >= 3:
                    self._queue_late_streak_message(sid, on_date, batch_id, streak)
                else:
                    self._queue_late_message(sid, on_date, batch_id, row.get('late_minutes'))
                summary['notified_late'].append(sid)

        return summary

    def _late_streak(self, student_id: str, on_date: str) -> int:
        """Count consecutive late days ending on on_date (backward)."""
        d = date.fromisoformat(date_str(on_date))
        streak = 0
        for i in range(14):  # safety bound
            check = (d - timedelta(days=i)).isoformat()
            rec = self._get_attendance_record(student_id, check)
            if rec and rec.get('status') == STATUS_LATE:
                streak += 1
            else:
                break
        return streak

    def _queue_absence_message(self, student_id: str, on_date: str, batch_id: str) -> None:
        if not self.notification_service:
            return
        # Templates are editable via NotificationService / config
        try:
            self.notification_service.enqueue(
                template_key='attendance.absence',
                recipient_student_id=student_id,
                context={'date': on_date, 'batch_id': batch_id},
            )
        except Exception:
            pass  # degrade gracefully offline / missing provider

    def _queue_late_message(
        self, student_id: str, on_date: str, batch_id: str, late_minutes: Optional[int]
    ) -> None:
        if not self.notification_service:
            return
        try:
            self.notification_service.enqueue(
                template_key='attendance.late',
                recipient_student_id=student_id,
                context={
                    'date': on_date,
                    'batch_id': batch_id,
                    'late_minutes': late_minutes,
                },
            )
        except Exception:
            pass

    def _queue_late_streak_message(
        self, student_id: str, on_date: str, batch_id: str, streak: int
    ) -> None:
        if not self.notification_service:
            return
        try:
            self.notification_service.enqueue(
                template_key='attendance.late_streak_3',
                recipient_student_id=student_id,
                context={
                    'date': on_date,
                    'batch_id': batch_id,
                    'streak': streak,
                },
            )
        except Exception:
            pass

    # ── Internals ─────────────────────────────────────────────────────

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
                pass  # never block core path


# Valid forced statuses for mark_manual
VALID_STATUSES_FOR_FORCE = frozenset({
    STATUS_PRESENT, STATUS_LATE, STATUS_ABSENT, STATUS_CROSS_BATCH,
})
