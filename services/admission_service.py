"""
Admission service — SPEC Module 1.

Responsibilities:
- Batch CRUD + templates
- Student admission with auto roll, duplicate detection
- Atomic roll/batch migration (full history)
- Per-admission join code generation (Module 8 primary path)
- All mutations audit-logged; core path works offline
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid
import copy

from models.base import TenantContext, DataAccessLayer
from models.admission import (
    Batch, BatchTemplate, Student, JoinCode, DuplicateMatch, MigrationRecord,
    days_to_bitmask, format_batch_display_name,
)
from services.roll_encoder import RollEncoder
from services.audit_service import AuditService
from services.config_service import ConfigService


HISTORY_TABLES = (
    'attendance',
    'payments',
    'exam_results',
    'threads',
    'join_codes',
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class DuplicateStudentError(Exception):
    """Raised when duplicate detection finds matches and force=False."""

    def __init__(self, matches: List[DuplicateMatch]):
        self.matches = matches
        reasons = '; '.join(m.reason for m in matches)
        super().__init__(f"Duplicate detected: {reasons}")


class AdmissionService:
    """Offline-first admission & batch management."""

    def __init__(
        self,
        tenant_context: TenantContext,
        data_layer: Optional[DataAccessLayer] = None,
        audit_service: Optional[AuditService] = None,
        config_service: Optional[ConfigService] = None,
        sync_engine=None,
    ):
        self.tenant_context = tenant_context
        self.data_layer = data_layer or DataAccessLayer(tenant_context)
        self.audit_service = audit_service or AuditService(tenant_context)
        self.config_service = config_service or ConfigService(tenant_context)
        self.sync_engine = sync_engine
        scheme = self.config_service.get('admission.roll_scheme', RollEncoder.SCHEME_BITMASK)
        self.roll_encoder = RollEncoder(scheme=scheme)

    # ── Batch management ──────────────────────────────────────────────

    def create_batch(
        self,
        days: List[str],
        hour: int,
        name: Optional[str] = None,
        template_id: Optional[str] = None,
        extra_sessions: Optional[List[Dict[str, Any]]] = None,
        actor_id: Optional[str] = None,
    ) -> str:
        """Create a batch slot. Name auto-generated unless overridden."""
        override = bool(name)
        # Always persist canonical lowercase day keys (sat/sun/mon/...) so
        # attendance weekday_key comparisons are reliable [BULLET].
        norm_days = []
        for d in days:
            key = d.strip().lower()[:3]
            if key not in ('sat', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri'):
                raise ValueError(f"Invalid day: {d}")
            if key not in norm_days:
                norm_days.append(key)
        batch = Batch(
            tenant_id=str(self.tenant_context.tenant_id),
            days=norm_days,
            hour=hour,
            name=name or '',
            name_override=override,
            template_id=template_id,
            extra_sessions=extra_sessions or [],
        )
        if not override:
            batch.name = format_batch_display_name(batch.days, batch.hour)

        record_id = self.data_layer.create('batches', batch.to_dict())
        # data_layer.create overwrites id — re-read and keep our id consistent
        stored = self.data_layer.get('batches', record_id)
        batch_id = str(record_id)

        self.audit_service.log_create(
            table_name='batches',
            record_id=record_id,
            new_state=stored or batch.to_dict(),
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._persist_audit()
        self._queue_sync('create', 'batches', batch_id, None, stored or batch.to_dict())
        return batch_id

    def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        return self.data_layer.get('batches', uuid.UUID(batch_id))

    def list_batches(self, active_only: bool = True) -> List[Dict[str, Any]]:
        batches = self.data_layer.get_all('batches')
        if active_only:
            batches = [b for b in batches if b.get('is_active', True)]
        return batches

    def update_batch(self, batch_id: str, actor_id: Optional[str] = None, **kwargs) -> bool:
        old = self.data_layer.get('batches', uuid.UUID(batch_id))
        if not old:
            return False

        updates = dict(kwargs)
        if 'days' in updates:
            updates['day_bitmask'] = days_to_bitmask(updates['days'])
            if not updates.get('name_override', old.get('name_override')):
                hour = updates.get('hour', old.get('hour', 14))
                updates['name'] = format_batch_display_name(updates['days'], hour)
        updates['updated_at'] = _utcnow()

        ok = self.data_layer.update('batches', uuid.UUID(batch_id), updates)
        if ok:
            new = self.data_layer.get('batches', uuid.UUID(batch_id))
            self.audit_service.log_update(
                table_name='batches',
                record_id=uuid.UUID(batch_id),
                old_state=old,
                new_state=new or updates,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._persist_audit()
            self._queue_sync('update', 'batches', batch_id, old, new)
        return ok

    def add_extra_session(
        self,
        batch_id: str,
        day: str,
        hour: int,
        expires_on: str,
        actor_id: Optional[str] = None,
    ) -> bool:
        """Add a temporary extra class session with expiry (SPEC [FLEX])."""
        batch = self.get_batch(batch_id)
        if not batch:
            return False
        sessions = list(batch.get('extra_sessions') or [])
        sessions.append({'day': day.lower()[:3], 'hour': hour, 'expires_on': expires_on})
        return self.update_batch(batch_id, actor_id=actor_id, extra_sessions=sessions)

    # ── Batch templates ───────────────────────────────────────────────

    def create_batch_template(
        self,
        name: str,
        coaching_type: str = 'hsc',
        default_days: Optional[List[str]] = None,
        default_hour: int = 14,
        exam_structure: Optional[Dict] = None,
        messaging_templates: Optional[Dict] = None,
        actor_id: Optional[str] = None,
    ) -> str:
        tmpl = BatchTemplate(
            tenant_id=str(self.tenant_context.tenant_id),
            name=name,
            coaching_type=coaching_type,
            default_days=default_days or [],
            default_hour=default_hour,
            exam_structure=exam_structure or {},
            messaging_templates=messaging_templates or {},
        )
        rid = self.data_layer.create('batch_templates', tmpl.to_dict())
        stored = self.data_layer.get('batch_templates', rid)
        self.audit_service.log_create(
            table_name='batch_templates',
            record_id=rid,
            new_state=stored or tmpl.to_dict(),
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._persist_audit()
        return str(rid)

    def list_templates(self) -> List[Dict[str, Any]]:
        return self.data_layer.get_all('batch_templates')

    def export_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        t = self.data_layer.get('batch_templates', uuid.UUID(template_id))
        if not t:
            return None
        # Never export AI system prompt content
        export = dict(t)
        export.pop('ai_prompt_content', None)
        return export

    # ── Duplicate detection ───────────────────────────────────────────

    def detect_duplicates(
        self,
        name: str,
        student_phone: str,
        parent_phones: Optional[List[str]] = None,
        exclude_id: Optional[str] = None,
    ) -> List[DuplicateMatch]:
        """
        Check same name+phone, or phone reused.
        Surfaces concrete conflicting record + reason (SPEC [BULLET]).
        """
        matches: List[DuplicateMatch] = []
        students = self.data_layer.get_all('students')
        # SPEC_v3 [HARDENED]: parent/WhatsApp phones explicitly excluded —
        # siblings routinely share a parent's phone. Only student's own phone.
        phones_to_check = set()
        if student_phone:
            phones_to_check.add(self._norm_phone(student_phone))

        name_norm = (name or '').strip().lower()

        for s in students:
            if exclude_id and s.get('id') == exclude_id:
                continue
            if not s.get('is_active', True):
                continue

            s_phone = self._norm_phone(s.get('student_phone', ''))
            s_name = (s.get('name') or '').strip().lower()

            # Phone collision — student's own phone only (SPEC_v3)
            colliding = None
            if s_phone and s_phone in phones_to_check:
                colliding = s_phone

            if colliding:
                reason = (
                    f"Phone number already registered to student {s.get('name')}, "
                    f"roll {s.get('roll') or '(none)'}"
                )
                matches.append(DuplicateMatch(
                    student_id=s['id'],
                    name=s.get('name', ''),
                    roll=s.get('roll', ''),
                    student_phone=s.get('student_phone', ''),
                    reason=reason,
                ))
                continue

            # Same name + same student phone
            if name_norm and s_name == name_norm and s_phone and student_phone:
                if s_phone == self._norm_phone(student_phone):
                    reason = (
                        f"Same name and phone as student {s.get('name')}, "
                        f"roll {s.get('roll') or '(none)'}"
                    )
                    matches.append(DuplicateMatch(
                        student_id=s['id'],
                        name=s.get('name', ''),
                        roll=s.get('roll', ''),
                        student_phone=s.get('student_phone', ''),
                        reason=reason,
                    ))

        return matches

    @staticmethod
    def _norm_phone(phone: str) -> str:
        return ''.join(c for c in (phone or '') if c.isdigit())

    # ── Admission / student ───────────────────────────────────────────

    def admit_student(
        self,
        name: str,
        batch_id: str,
        student_phone: str = '',
        parent_phones: Optional[List[str]] = None,
        whatsapp: str = '',
        roll: Optional[str] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
        force: bool = False,
        actor_id: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        """
        Admit a student.

        Returns (student_id, join_code).
        Raises DuplicateStudentError unless force=True (idempotent proceed).
        """
        parent_phones = parent_phones or []

        # Duplicate detection first
        dupes = self.detect_duplicates(name, student_phone, parent_phones)
        if dupes and not force:
            raise DuplicateStudentError(dupes)

        batch = self.get_batch(batch_id)
        if not batch:
            raise ValueError(f"Batch not found: {batch_id}")

        # Auto-generate roll if not provided
        if not roll:
            existing = [s.get('roll', '') for s in self.data_layer.get_all('students') if s.get('roll')]
            serial = self.roll_encoder.next_serial(
                existing,
                batch.get('days') or [],
                int(batch.get('hour', 14)),
            )
            roll = self.roll_encoder.encode(
                batch.get('days') or [],
                int(batch.get('hour', 14)),
                serial,
            )

        student = Student(
            tenant_id=str(self.tenant_context.tenant_id),
            name=name.strip(),
            batch_id=batch_id,
            roll=roll,
            student_phone=student_phone,
            parent_phones=parent_phones,
            whatsapp=whatsapp or student_phone,
            custom_fields=custom_fields or {},
        )

        rid = self.data_layer.create('students', student.to_dict())
        stored = self.data_layer.get('students', rid)
        student_id = str(rid)

        self.audit_service.log_create(
            table_name='students',
            record_id=rid,
            new_state=stored or student.to_dict(),
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._persist_audit()
        self._queue_sync('create', 'students', student_id, None, stored or student.to_dict())

        # Generate per-admission join code (Module 8 primary)
        join_code = self.generate_join_code(student_id, actor_id=actor_id)
        return student_id, join_code

    def get_student(self, student_id: str) -> Optional[Dict[str, Any]]:
        return self.data_layer.get('students', uuid.UUID(student_id))

    def list_students(self, batch_id: Optional[str] = None, active_only: bool = True) -> List[Dict[str, Any]]:
        students = self.data_layer.get_all('students')
        if active_only:
            students = [s for s in students if s.get('is_active', True)]
        if batch_id:
            students = [s for s in students if s.get('batch_id') == batch_id]
        return students

    def update_student(
        self,
        student_id: str,
        actor_id: Optional[str] = None,
        force: bool = False,
        **kwargs,
    ) -> bool:
        """Edit student fields (not roll/batch — use migrate for those)."""
        old = self.get_student(student_id)
        if not old:
            return False

        # Guard: roll/batch changes must go through migrate
        if 'roll' in kwargs or 'batch_id' in kwargs:
            raise ValueError(
                "Use migrate_student_roll_batch() for roll/batch changes "
                "to preserve full history atomically"
            )

        # Duplicate check if phone/name changing
        name = kwargs.get('name', old.get('name', ''))
        phone = kwargs.get('student_phone', old.get('student_phone', ''))
        parents = kwargs.get('parent_phones', old.get('parent_phones'))
        if 'name' in kwargs or 'student_phone' in kwargs or 'parent_phones' in kwargs:
            dupes = self.detect_duplicates(name, phone, parents, exclude_id=student_id)
            if dupes and not force:
                raise DuplicateStudentError(dupes)

        updates = dict(kwargs)
        updates['updated_at'] = _utcnow()
        ok = self.data_layer.update('students', uuid.UUID(student_id), updates)
        if ok:
            new = self.get_student(student_id)
            self.audit_service.log_update(
                table_name='students',
                record_id=uuid.UUID(student_id),
                old_state=old,
                new_state=new or updates,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._persist_audit()
            self._queue_sync('update', 'students', student_id, old, new)
        return ok

    # ── Atomic roll/batch migration ───────────────────────────────────

    def migrate_student_roll_batch(
        self,
        student_id: str,
        new_batch_id: Optional[str] = None,
        new_roll: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> MigrationRecord:
        """
        Atomically migrate student to new batch and/or roll.
        Moves full history (attendance, payments, results, threads, join_codes).
        All-or-nothing; logs the migration itself (SPEC [BULLET]).
        """
        student = self.get_student(student_id)
        if not student:
            raise ValueError(f"Student not found: {student_id}")

        old_batch_id = student.get('batch_id', '')
        old_roll = student.get('roll', '')
        target_batch_id = new_batch_id or old_batch_id

        batch = self.get_batch(target_batch_id)
        if not batch:
            raise ValueError(f"Target batch not found: {target_batch_id}")

        # Generate new roll if moving batch and no explicit roll
        if not new_roll:
            if target_batch_id != old_batch_id:
                existing = [
                    s.get('roll', '') for s in self.data_layer.get_all('students')
                    if s.get('roll') and s.get('id') != student_id
                ]
                serial = self.roll_encoder.next_serial(
                    existing,
                    batch.get('days') or [],
                    int(batch.get('hour', 14)),
                )
                new_roll = self.roll_encoder.encode(
                    batch.get('days') or [],
                    int(batch.get('hour', 14)),
                    serial,
                )
            else:
                new_roll = old_roll

        if new_roll == old_roll and target_batch_id == old_batch_id:
            # No-op
            return MigrationRecord(
                tenant_id=str(self.tenant_context.tenant_id),
                student_id=student_id,
                old_roll=old_roll,
                new_roll=new_roll,
                old_batch_id=old_batch_id,
                new_batch_id=target_batch_id,
                tables_migrated=[],
                records_moved=0,
                actor_id=actor_id,
                status='completed',
            )

        # Snapshot for rollback
        snapshots: Dict[str, List[Dict]] = {}
        records_moved = 0
        tables_migrated: List[str] = []

        try:
            # Migrate history tables: rewrite student_id / roll / batch_id refs
            for table in HISTORY_TABLES:
                rows = self.data_layer.get_all(table)
                # Filter rows belonging to this student (by student_id or roll)
                owned = [
                    r for r in rows
                    if r.get('student_id') == student_id
                    or r.get('admission_id') == student_id
                    or (r.get('roll') and r.get('roll') == old_roll)
                ]
                if not owned:
                    continue

                snapshots[table] = copy.deepcopy(owned)
                for row in owned:
                    rid = row.get('id')
                    if not rid:
                        continue
                    patch = {'updated_at': _utcnow()}
                    if 'roll' in row:
                        patch['roll'] = new_roll
                    if 'batch_id' in row:
                        patch['batch_id'] = target_batch_id
                    # student_id / admission_id stay the same (identity is admission_id)
                    self.data_layer.update(table, uuid.UUID(rid), patch)
                    records_moved += 1
                tables_migrated.append(table)

            # Update student record itself
            old_student = dict(student)
            ok = self.data_layer.update(
                'students',
                uuid.UUID(student_id),
                {
                    'batch_id': target_batch_id,
                    'roll': new_roll,
                    'updated_at': _utcnow(),
                },
            )
            if not ok:
                raise RuntimeError("Failed to update student record during migration")

            new_student = self.get_student(student_id)
            self.audit_service.log_update(
                table_name='students',
                record_id=uuid.UUID(student_id),
                old_state=old_student,
                new_state=new_student or {},
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )

            migration = MigrationRecord(
                tenant_id=str(self.tenant_context.tenant_id),
                student_id=student_id,
                old_roll=old_roll,
                new_roll=new_roll,
                old_batch_id=old_batch_id,
                new_batch_id=target_batch_id,
                tables_migrated=tables_migrated,
                records_moved=records_moved,
                actor_id=actor_id,
                status='completed',
            )
            mid = self.data_layer.create('migration_logs', migration.to_dict())
            migration.id = str(mid)

            self.audit_service.log_create(
                table_name='migration_logs',
                record_id=mid,
                new_state=migration.to_dict(),
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._persist_audit()
            self._queue_sync('update', 'students', student_id, old_student, new_student)
            return migration

        except Exception as e:
            # Rollback from snapshots
            for table, rows in snapshots.items():
                for row in rows:
                    rid = row.get('id')
                    if rid:
                        # Restore original values
                        self.data_layer.update(table, uuid.UUID(rid), row)

            # Restore student if partially updated
            self.data_layer.update(
                'students',
                uuid.UUID(student_id),
                {'batch_id': old_batch_id, 'roll': old_roll},
            )

            failed = MigrationRecord(
                tenant_id=str(self.tenant_context.tenant_id),
                student_id=student_id,
                old_roll=old_roll,
                new_roll=new_roll,
                old_batch_id=old_batch_id,
                new_batch_id=target_batch_id,
                tables_migrated=tables_migrated,
                records_moved=0,
                actor_id=actor_id,
                status='rolled_back',
                error_message=str(e),
            )
            try:
                self.data_layer.create('migration_logs', failed.to_dict())
            except Exception:
                pass
            raise RuntimeError(f"Migration failed and was rolled back: {e}") from e

    # ── Join codes (Module 8 primary path) ────────────────────────────

    def generate_join_code(
        self,
        admission_id: str,
        expiry_days: int = 30,
        actor_id: Optional[str] = None,
    ) -> str:
        """
        Generate per-admission join code. Invalidates prior unused codes
        for the same admission (SPEC: regenerate auto-invalidates prior).
        """
        # Invalidate existing unused codes
        existing = self.data_layer.get_all('join_codes')
        for jc in existing:
            if jc.get('admission_id') == admission_id and not jc.get('is_used'):
                self.data_layer.update(
                    'join_codes',
                    uuid.UUID(jc['id']),
                    {'is_used': True, 'used_at': _utcnow()},  # soft-invalidate
                )

        expires = (datetime.now(timezone.utc) + timedelta(days=expiry_days)).isoformat()
        code = JoinCode(
            tenant_id=str(self.tenant_context.tenant_id),
            admission_id=admission_id,
            expires_at=expires,
        )
        rid = self.data_layer.create('join_codes', code.to_dict())
        stored = self.data_layer.get('join_codes', rid)
        self.audit_service.log_create(
            table_name='join_codes',
            record_id=rid,
            new_state=stored or code.to_dict(),
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._persist_audit()
        return code.code

    def link_account(
        self,
        admission_id: str,
        cohortos_account_id: str,
        join_code: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> bool:
        """
        link(admission_id, cohortos_account_id) — single underlying operation
        for both QR/code and staff-manual paths (SPEC Module 8 [LOCKED]).
        """
        student = self.get_student(admission_id)
        if not student:
            raise ValueError(f"Admission not found: {admission_id}")

        if join_code:
            # Validate code
            codes = self.data_layer.get_all('join_codes')
            match = None
            for jc in codes:
                if (
                    jc.get('admission_id') == admission_id
                    and jc.get('code') == join_code.upper()
                    and not jc.get('is_used')
                ):
                    # Check expiry
                    if jc.get('expires_at') and jc['expires_at'] < _utcnow():
                        raise ValueError("Join code has expired")
                    match = jc
                    break
            if not match:
                raise ValueError("Invalid or already-used join code")

            self.data_layer.update(
                'join_codes',
                uuid.UUID(match['id']),
                {
                    'is_used': True,
                    'used_at': _utcnow(),
                    'used_by_account_id': cohortos_account_id,
                },
            )

        old = dict(student)
        ok = self.data_layer.update(
            'students',
            uuid.UUID(admission_id),
            {
                'cohortos_account_id': cohortos_account_id,
                'updated_at': _utcnow(),
            },
        )
        if ok:
            new = self.get_student(admission_id)
            self.audit_service.log_update(
                table_name='students',
                record_id=uuid.UUID(admission_id),
                old_state=old,
                new_state=new or {},
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._persist_audit()
        return ok

    # ── Helpers ───────────────────────────────────────────────────────

    def _persist_audit(self):
        if self.audit_service:
            self.audit_service.save_logs_to_storage(self.data_layer)

    def _queue_sync(self, op_type, table, record_id, old_state, new_state):
        if not self.sync_engine:
            return
        if self.tenant_context.mode not in ('offline-first', 'hybrid'):
            return
        try:
            from models.sync import SyncOperation
            self.sync_engine.queue_operation(SyncOperation(
                operation_type=op_type,
                table_name=table,
                record_id=str(record_id),
                tenant_id=str(self.tenant_context.tenant_id),
                old_state=old_state,
                new_state=new_state or {},
            ))
        except Exception:
            pass  # never block core path on sync failure
