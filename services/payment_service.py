"""
Payment service — SPEC Module 3.

- Default: paid/unpaid per month (no amount)
- Optional amount + receipt mode (config)
- [BULLET] Lock = manual teacher action; locked records immutable except owner unlock
- [BULLET] Green/white notify flag: white persists, no auto-reset
- [LOCKED] Irregularity exclusion reuses AttendanceService threshold (one setting)
- bKash/Nagad deep-link in reminder context
- Teacher delayed-payment summary (opt-in)
- Offline-first, tenant-scoped, audit-logged, sync-ready
"""

from __future__ import annotations

from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional, Tuple
import uuid

from models.base import TenantContext, DataAccessLayer
from models.payment import (
    PaymentRecord, PaymentUnlockEvent,
    STATUS_PAID, STATUS_UNPAID, STATUS_WAIVED, NOTIFY_GREEN, NOTIFY_WHITE,
    _utcnow,
)
from services.audit_service import AuditService
from services.config_service import ConfigService


# Config keys
CFG_AMOUNT_MODE = 'payment.amount_mode_enabled'          # bool, default False
CFG_TRIGGER_DAY = 'payment.delayed_trigger_day'          # 1–28, default 10
CFG_TRIGGER_TARGET = 'payment.delayed_trigger_target'    # 'previous' | 'current'
CFG_BKASH_LINK = 'payment.bkash_deeplink'
CFG_NAGAD_LINK = 'payment.nagad_deeplink'
CFG_TEACHER_SUMMARY = 'payment.teacher_summary_enabled'  # bool


class PaymentLockedError(Exception):
    """Raised when attempting to mutate a locked payment without owner unlock."""
    pass


class PaymentService:
    """Offline-first payment tracking with locking and delayed messaging."""

    def __init__(
        self,
        tenant_context: TenantContext,
        data_layer: Optional[DataAccessLayer] = None,
        audit_service: Optional[AuditService] = None,
        config_service: Optional[ConfigService] = None,
        attendance_service=None,
        notification_service=None,
        sync_engine=None,
    ):
        self.tenant_context = tenant_context
        self.data_layer = data_layer or DataAccessLayer(tenant_context)
        self.audit_service = audit_service or AuditService(tenant_context)
        self.config_service = config_service or ConfigService(tenant_context)
        self.attendance_service = attendance_service
        self.notification_service = notification_service
        self.sync_engine = sync_engine

    # ── Config ────────────────────────────────────────────────────────

    def is_amount_mode(self) -> bool:
        return bool(self.config_service.get(CFG_AMOUNT_MODE, False))

    def set_amount_mode(self, enabled: bool) -> None:
        self.config_service.set(CFG_AMOUNT_MODE, bool(enabled))

    def get_trigger_day(self) -> int:
        return int(self.config_service.get(CFG_TRIGGER_DAY, 10) or 10)

    def get_trigger_target(self) -> str:
        t = self.config_service.get(CFG_TRIGGER_TARGET, 'previous') or 'previous'
        return t if t in ('previous', 'current') else 'previous'

    def get_payment_links(self) -> Dict[str, str]:
        return {
            'bkash': self.config_service.get(CFG_BKASH_LINK, '') or '',
            'nagad': self.config_service.get(CFG_NAGAD_LINK, '') or '',
        }

    def set_payment_links(self, bkash: str = '', nagad: str = '') -> None:
        if bkash is not None:
            self.config_service.set(CFG_BKASH_LINK, bkash)
        if nagad is not None:
            self.config_service.set(CFG_NAGAD_LINK, nagad)

    # ── Core CRUD ─────────────────────────────────────────────────────

    def get_payment(
        self,
        student_id: str,
        year: int,
        month: int,
    ) -> Optional[Dict[str, Any]]:
        for r in self.data_layer.get_all('payment_records'):
            if (r.get('student_id') == student_id
                    and int(r.get('year', 0)) == year
                    and int(r.get('month', 0)) == month):
                return r
        return None

    def ensure_payment(
        self,
        student_id: str,
        year: int,
        month: int,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return existing or create unpaid/unlocked/green record."""
        existing = self.get_payment(student_id, year, month)
        if existing:
            return existing
        student = self.data_layer.get('students', uuid.UUID(student_id))
        if not student:
            raise ValueError(f"Student {student_id} not found")
        rec = PaymentRecord(
            tenant_id=str(self.tenant_context.tenant_id),
            student_id=student_id,
            batch_id=student.get('batch_id', ''),
            roll=student.get('roll', ''),
            year=year,
            month=month,
            status=STATUS_UNPAID,
            locked=False,
            notify_flag=NOTIFY_GREEN,
        )
        rid = self.data_layer.create('payment_records', rec.to_dict())
        stored = self.data_layer.get('payment_records', rid)
        self.audit_service.log_create(
            table_name='payment_records',
            record_id=rid,
            new_state=stored or rec.to_dict(),
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._queue_sync('create', 'payment_records', str(rid), None, stored)
        # Mirror stub table for Portion 2 migration compatibility
        self._mirror_stub(stored or rec.to_dict())
        return stored or rec.to_dict()

    def list_student_payments(
        self,
        student_id: str,
        year: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        rows = [
            r for r in self.data_layer.get_all('payment_records')
            if r.get('student_id') == student_id
        ]
        if year is not None:
            rows = [r for r in rows if int(r.get('year', 0)) == year]
        rows.sort(key=lambda r: (int(r.get('year', 0)), int(r.get('month', 0))))
        return rows

    def list_batch_payments(
        self,
        batch_id: str,
        year: int,
        month: int,
    ) -> List[Dict[str, Any]]:
        """All students in batch with their status for the month (creates unpaid if missing)."""
        students = [
            s for s in self.data_layer.get_all('students')
            if s.get('batch_id') == batch_id and s.get('is_active', True)
        ]
        out = []
        for s in students:
            rec = self.ensure_payment(s['id'], year, month)
            out.append({
                'student_id': s['id'],
                'name': s.get('name'),
                'roll': s.get('roll'),
                'status': rec.get('status'),
                'locked': bool(rec.get('locked')),
                'notify_flag': rec.get('notify_flag', NOTIFY_GREEN),
                'amount': rec.get('amount'),
                'record': rec,
            })
        return out

    # ── Mark paid / unpaid (unlocked only) ────────────────────────────

    def mark_paid(
        self,
        student_id: str,
        year: int,
        month: int,
        amount: Optional[float] = None,
        receipt_ref: Optional[str] = None,
        actor_id: Optional[str] = None,
        notes: str = '',
    ) -> Dict[str, Any]:
        """
        Set status=paid. Does NOT lock — locking is a separate explicit action.
        Fails if already locked.
        """
        rec = self.ensure_payment(student_id, year, month, actor_id=actor_id)
        if rec.get('locked'):
            raise PaymentLockedError(
                f"Payment {year}-{month:02d} for student {student_id} is locked"
            )
        updates: Dict[str, Any] = {
            'status': STATUS_PAID,
            'updated_at': _utcnow(),
        }
        if notes:
            updates['notes'] = notes
        if self.is_amount_mode():
            if amount is not None:
                updates['amount'] = float(amount)
            if receipt_ref is not None:
                updates['receipt_ref'] = receipt_ref
        return self._apply_update(rec, updates, actor_id)

    def mark_unpaid(
        self,
        student_id: str,
        year: int,
        month: int,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Revert to unpaid. Fails if locked."""
        rec = self.ensure_payment(student_id, year, month, actor_id=actor_id)
        if rec.get('locked'):
            raise PaymentLockedError(
                f"Payment {year}-{month:02d} for student {student_id} is locked"
            )
        return self._apply_update(rec, {
            'status': STATUS_UNPAID,
            'amount': None,
            'receipt_ref': None,
            'updated_at': _utcnow(),
        }, actor_id)

    # ── Locking [BULLET] ──────────────────────────────────────────────

    def mark_waived(
        self,
        student_id: str,
        year: int,
        month: int,
        actor_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        Owner-only Waived status (SPEC_v3 [HARDENED]).
        Scholarships / sibling discounts / fee waivers — excluded from payment nags.
        Requires a one-line reason; audit-logged.
        """
        if not (reason or "").strip():
            raise ValueError("Waived status requires a one-line reason")
        rec = self.ensure_payment(student_id, year, month, actor_id=actor_id)
        if rec.get("locked"):
            raise PaymentLockedError(
                f"Payment {year}-{month:02d} for student {student_id} is locked"
            )
        notes = (rec.get("notes") or "")
        if notes:
            notes = notes + f" [waived: {reason.strip()}]"
        else:
            notes = f"[waived: {reason.strip()}]"
        updates = {
            "status": STATUS_WAIVED,
            "notes": notes,
            "updated_at": _utcnow(),
        }
        return self._apply_update(rec, updates, actor_id)

    def lock_payment(
        self,
        student_id: str,
        year: int,
        month: int,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Explicit lock. Typically called after mark_paid, but can lock any state.
        Once locked, only owner unlock can mutate.
        """
        rec = self.ensure_payment(student_id, year, month, actor_id=actor_id)
        if rec.get('locked'):
            return rec  # idempotent
        updates = {
            'locked': True,
            'locked_at': _utcnow(),
            'locked_by': actor_id or str(self.tenant_context.tenant_id),
            'status': STATUS_PAID,  # locking implies paid (SPEC: "marks it paid and locks")
            'updated_at': _utcnow(),
        }
        return self._apply_update(rec, updates, actor_id)

    def unlock_payment(
        self,
        student_id: str,
        year: int,
        month: int,
        actor_id: str,
        reason: str = '',
        is_owner: bool = True,
    ) -> Dict[str, Any]:
        """
        Owner-only unlock. Audit-logged. Creates PaymentUnlockEvent.
        is_owner must be True (caller enforces RBAC); service rejects otherwise.
        """
        if not is_owner:
            raise PermissionError("Only owner can unlock a locked payment")
        if not actor_id:
            raise ValueError("actor_id required for unlock")
        rec = self.get_payment(student_id, year, month)
        if not rec:
            raise ValueError("Payment record not found")
        if not rec.get('locked'):
            return rec  # already unlocked

        prev_status = rec.get('status', STATUS_PAID)
        updates = {
            'locked': False,
            'unlocked_at': _utcnow(),
            'unlocked_by': actor_id,
            'updated_at': _utcnow(),
        }
        result = self._apply_update(rec, updates, actor_id)

        # Dedicated unlock event
        event = PaymentUnlockEvent(
            tenant_id=str(self.tenant_context.tenant_id),
            payment_id=rec['id'],
            student_id=student_id,
            year=year,
            month=month,
            unlocked_by=actor_id,
            reason=reason,
            previous_status=prev_status,
        )
        eid = self.data_layer.create('payment_unlock_events', event.to_dict())
        self.audit_service.log_create(
            table_name='payment_unlock_events',
            record_id=eid,
            new_state=event.to_dict(),
            actor_id=uuid.UUID(actor_id),
        )
        return result

    # ── Green / white box [BULLET] ────────────────────────────────────

    def set_notify_flag(
        self,
        student_id: str,
        year: int,
        month: int,
        flag: str,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Toggle green (will receive) / white (will not).
        White stays white — no auto-reset.
        Allowed even when locked (notify preference is independent of payment status).
        """
        if flag not in (NOTIFY_GREEN, NOTIFY_WHITE):
            raise ValueError(f"flag must be green or white, got {flag}")
        rec = self.ensure_payment(student_id, year, month, actor_id=actor_id)
        return self._apply_update(rec, {
            'notify_flag': flag,
            'updated_at': _utcnow(),
        }, actor_id, allow_when_locked=True)

    def set_notify_white(self, student_id: str, year: int, month: int, actor_id: Optional[str] = None):
        return self.set_notify_flag(student_id, year, month, NOTIFY_WHITE, actor_id)

    def set_notify_green(self, student_id: str, year: int, month: int, actor_id: Optional[str] = None):
        return self.set_notify_flag(student_id, year, month, NOTIFY_GREEN, actor_id)

    # ── Delayed-payment messaging ─────────────────────────────────────

    def list_delayed_candidates(
        self,
        batch_id: str,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """
        Students eligible for delayed-payment message this cycle:
        - status == unpaid
        - notify_flag == green
        - NOT irregular (shared threshold from Attendance)
        Returns green list + white list + irregular-excluded list.
        """
        rows = self.list_batch_payments(batch_id, year, month)
        green, white, irregular = [], [], []
        for row in rows:
            if row['status'] in (STATUS_PAID, STATUS_WAIVED):
                continue
            sid = row['student_id']
            if self._is_irregular(sid, year, month, batch_id):
                irregular.append(row)
                continue
            if row.get('notify_flag') == NOTIFY_WHITE:
                white.append(row)
            else:
                green.append(row)
        return {
            'year': year,
            'month': month,
            'batch_id': batch_id,
            'will_notify': green,
            'suppressed_white': white,
            'excluded_irregular': irregular,
            'links': self.get_payment_links(),
        }

    def send_delayed_messages(
        self,
        batch_id: str,
        year: int,
        month: int,
        actor_id: Optional[str] = None,
        send_teacher_summary: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Queue delayed-payment messages for green unpaid non-irregular students.
        Optionally queue teacher summary.
        """
        candidates = self.list_delayed_candidates(batch_id, year, month)
        notified = []
        for row in candidates['will_notify']:
            self._queue_payment_reminder(row['student_id'], year, month, batch_id)
            notified.append(row['student_id'])

        summary_sent = False
        do_summary = (
            send_teacher_summary
            if send_teacher_summary is not None
            else bool(self.config_service.get(CFG_TEACHER_SUMMARY, False))
        )
        if do_summary and (notified or candidates['excluded_irregular']):
            self._queue_teacher_summary(batch_id, year, month, candidates)
            summary_sent = True

        return {
            'notified_student_ids': notified,
            'suppressed_white_count': len(candidates['suppressed_white']),
            'excluded_irregular_count': len(candidates['excluded_irregular']),
            'teacher_summary_sent': summary_sent,
            'links': candidates['links'],
        }

    def _is_irregular(
        self,
        student_id: str,
        year: int,
        month: int,
        batch_id: Optional[str] = None,
    ) -> bool:
        """Reuse AttendanceService irregularity threshold (SPEC [LOCKED])."""
        if self.attendance_service is None:
            return False  # cannot exclude without attendance data
        try:
            return self.attendance_service.is_irregular(
                student_id, year, month, batch_id
            )
        except Exception:
            return False

    def _queue_payment_reminder(
        self, student_id: str, year: int, month: int, batch_id: str
    ) -> None:
        if not self.notification_service:
            return
        links = self.get_payment_links()
        try:
            self.notification_service.enqueue(
                template_key='payment.delayed',
                recipient_student_id=student_id,
                context={
                    'year': year,
                    'month': month,
                    'batch_id': batch_id,
                    'bkash_link': links.get('bkash', ''),
                    'nagad_link': links.get('nagad', ''),
                },
            )
        except Exception:
            pass

    def _queue_teacher_summary(
        self, batch_id: str, year: int, month: int, candidates: Dict
    ) -> None:
        if not self.notification_service:
            return
        try:
            self.notification_service.enqueue(
                template_key='payment.teacher_summary',
                recipient_role='owner',
                context={
                    'year': year,
                    'month': month,
                    'batch_id': batch_id,
                    'will_notify_count': len(candidates['will_notify']),
                    'white_count': len(candidates['suppressed_white']),
                    'irregular_count': len(candidates['excluded_irregular']),
                },
            )
        except Exception:
            pass

    # ── Bulk helpers ──────────────────────────────────────────────────

    def bulk_lock_paid(
        self,
        batch_id: str,
        year: int,
        month: int,
        student_ids: List[str],
        actor_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """Mark paid + lock for a list of students. Returns {sid: record_id|error}."""
        results = {}
        for sid in student_ids:
            try:
                self.mark_paid(sid, year, month, actor_id=actor_id)
                rec = self.lock_payment(sid, year, month, actor_id=actor_id)
                results[sid] = rec['id']
            except Exception as e:
                results[sid] = f"ERROR: {e}"
        return results

    # ── Internals ─────────────────────────────────────────────────────

    def _apply_update(
        self,
        rec: Dict[str, Any],
        updates: Dict[str, Any],
        actor_id: Optional[str],
        allow_when_locked: bool = False,
    ) -> Dict[str, Any]:
        if rec.get('locked') and not allow_when_locked:
            # Allow only unlock path; other mutations blocked
            if not (updates.get('locked') is False):
                raise PaymentLockedError(
                    f"Payment record {rec.get('id')} is locked"
                )
        old = dict(rec)
        ok = self.data_layer.update(
            'payment_records', uuid.UUID(rec['id']), updates
        )
        if not ok:
            raise RuntimeError("Failed to update payment record")
        new = self.data_layer.get('payment_records', uuid.UUID(rec['id']))
        self.audit_service.log_update(
            table_name='payment_records',
            record_id=uuid.UUID(rec['id']),
            old_state=old,
            new_state=new,
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._queue_sync('update', 'payment_records', rec['id'], old, new)
        self._mirror_stub(new or {**old, **updates})
        return new or {**old, **updates}

    def _mirror_stub(self, data: Dict[str, Any]) -> None:
        """Keep Portion 2 HISTORY_TABLES `payments` stub in rough sync for migration."""
        try:
            stub = {
                'id': data.get('id'),
                'tenant_id': data.get('tenant_id'),
                'student_id': data.get('student_id'),
                'roll': data.get('roll', ''),
                'batch_id': data.get('batch_id', ''),
                'month': data.get('month_key') or f"{data.get('year')}-{int(data.get('month', 0)):02d}",
                'status': data.get('status'),
                'locked': 1 if data.get('locked') else 0,
                'created_at': data.get('created_at'),
                'updated_at': data.get('updated_at'),
            }
            existing = None
            for r in self.data_layer.get_all('payments'):
                if r.get('id') == stub['id']:
                    existing = r
                    break
            if existing:
                self.data_layer.update('payments', uuid.UUID(stub['id']), stub)
            else:
                # create expects to set id — inject
                self.data_layer.create('payments', stub)
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
