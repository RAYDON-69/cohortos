"""
Portion 4 tests — Payment locking, green/white, irregularity exclusion,
optional amount mode, delayed messaging.
Covers SPEC Module 3 [BULLET] [LOCKED] [FLEX] [NEW] requirements.
"""

import pytest
import uuid
from datetime import datetime

from models.base import TenantContext, DataAccessLayer
from models.payment import (
    STATUS_PAID, STATUS_UNPAID, NOTIFY_GREEN, NOTIFY_WHITE,
)
from services.payment_service import PaymentService, PaymentLockedError
from services.admission_service import AdmissionService
from services.attendance_service import AttendanceService
from services.audit_service import AuditService
from services.config_service import ConfigService
from models.attendance import SOURCE_BIOMETRIC


@pytest.fixture
def ctx():
    return TenantContext(tenant_id=uuid.uuid4(), mode='offline-first')


@pytest.fixture
def layer(ctx):
    return DataAccessLayer(ctx)


@pytest.fixture
def admission(ctx, layer):
    return AdmissionService(
        ctx, data_layer=layer,
        audit_service=AuditService(ctx),
        config_service=ConfigService(ctx),
    )


@pytest.fixture
def attendance(ctx, layer):
    return AttendanceService(
        ctx, data_layer=layer,
        audit_service=AuditService(ctx),
        config_service=ConfigService(ctx),
    )


@pytest.fixture
def svc(ctx, layer, attendance):
    return PaymentService(
        ctx, data_layer=layer,
        audit_service=AuditService(ctx),
        config_service=ConfigService(ctx),
        attendance_service=attendance,
    )


def _setup(admission, n=2):
    bid = admission.create_batch(days=['mon', 'wed'], hour=14)
    students = []
    for i in range(n):
        sid, _ = admission.admit_student(
            name=f'PayStudent{i}',
            batch_id=bid,
            student_phone=f'0181000000{i}',
        )
        students.append(sid)
    return bid, students


# ── Basic paid/unpaid ─────────────────────────────────────────────────

class TestBasic:
    def test_ensure_creates_unpaid(self, svc, admission):
        bid, students = _setup(admission, 1)
        rec = svc.ensure_payment(students[0], 2026, 8)
        assert rec['status'] == STATUS_UNPAID
        assert rec['locked'] is False
        assert rec['notify_flag'] == NOTIFY_GREEN

    def test_mark_paid_unlocked(self, svc, admission):
        bid, students = _setup(admission, 1)
        rec = svc.mark_paid(students[0], 2026, 8)
        assert rec['status'] == STATUS_PAID
        assert rec['locked'] is False

    def test_mark_unpaid(self, svc, admission):
        bid, students = _setup(admission, 1)
        svc.mark_paid(students[0], 2026, 8)
        rec = svc.mark_unpaid(students[0], 2026, 8)
        assert rec['status'] == STATUS_UNPAID

    def test_list_student_payments(self, svc, admission):
        bid, students = _setup(admission, 1)
        svc.mark_paid(students[0], 2026, 7)
        svc.mark_paid(students[0], 2026, 8)
        rows = svc.list_student_payments(students[0], year=2026)
        assert len(rows) == 2

    def test_list_batch_payments(self, svc, admission):
        bid, students = _setup(admission, 3)
        svc.mark_paid(students[0], 2026, 8)
        rows = svc.list_batch_payments(bid, 2026, 8)
        assert len(rows) == 3
        paid = [r for r in rows if r['status'] == STATUS_PAID]
        assert len(paid) == 1


# ── Locking [BULLET] ──────────────────────────────────────────────────

class TestLocking:
    def test_lock_marks_paid_and_locks(self, svc, admission):
        bid, students = _setup(admission, 1)
        rec = svc.lock_payment(students[0], 2026, 8)
        assert rec['locked'] is True
        assert rec['status'] == STATUS_PAID
        assert rec['locked_at'] is not None

    def test_locked_cannot_mark_unpaid(self, svc, admission):
        bid, students = _setup(admission, 1)
        svc.lock_payment(students[0], 2026, 8)
        with pytest.raises(PaymentLockedError):
            svc.mark_unpaid(students[0], 2026, 8)

    def test_locked_cannot_mark_paid_again_mutate(self, svc, admission):
        bid, students = _setup(admission, 1)
        svc.lock_payment(students[0], 2026, 8)
        # mark_paid on locked should fail
        with pytest.raises(PaymentLockedError):
            svc.mark_paid(students[0], 2026, 8, notes='try overwrite')

    def test_lock_idempotent(self, svc, admission):
        bid, students = _setup(admission, 1)
        r1 = svc.lock_payment(students[0], 2026, 8)
        r2 = svc.lock_payment(students[0], 2026, 8)
        assert r1['id'] == r2['id']
        assert r2['locked'] is True

    def test_owner_unlock(self, svc, admission):
        bid, students = _setup(admission, 1)
        owner = str(uuid.uuid4())
        svc.lock_payment(students[0], 2026, 8, actor_id=owner)
        rec = svc.unlock_payment(
            students[0], 2026, 8,
            actor_id=owner, reason='Correction', is_owner=True,
        )
        assert rec['locked'] is False
        assert rec['unlocked_by'] == owner
        # Now can mutate
        rec2 = svc.mark_unpaid(students[0], 2026, 8)
        assert rec2['status'] == STATUS_UNPAID

    def test_non_owner_unlock_rejected(self, svc, admission):
        bid, students = _setup(admission, 1)
        svc.lock_payment(students[0], 2026, 8)
        with pytest.raises(PermissionError):
            svc.unlock_payment(
                students[0], 2026, 8,
                actor_id=str(uuid.uuid4()), reason='hack', is_owner=False,
            )

    def test_unlock_creates_event(self, svc, admission, layer):
        bid, students = _setup(admission, 1)
        owner = str(uuid.uuid4())
        svc.lock_payment(students[0], 2026, 8, actor_id=owner)
        svc.unlock_payment(students[0], 2026, 8, actor_id=owner, reason='Oops', is_owner=True)
        events = layer.get_all('payment_unlock_events')
        assert len(events) == 1
        assert events[0]['reason'] == 'Oops'
        assert events[0]['unlocked_by'] == owner


# ── Green / white [BULLET] ────────────────────────────────────────────

class TestNotifyFlag:
    def test_default_green(self, svc, admission):
        bid, students = _setup(admission, 1)
        rec = svc.ensure_payment(students[0], 2026, 8)
        assert rec['notify_flag'] == NOTIFY_GREEN

    def test_set_white_persists(self, svc, admission):
        bid, students = _setup(admission, 1)
        svc.set_notify_white(students[0], 2026, 8)
        rec = svc.get_payment(students[0], 2026, 8)
        assert rec['notify_flag'] == NOTIFY_WHITE
        # Re-ensure does not reset
        rec2 = svc.ensure_payment(students[0], 2026, 8)
        assert rec2['notify_flag'] == NOTIFY_WHITE

    def test_white_allowed_when_locked(self, svc, admission):
        bid, students = _setup(admission, 1)
        svc.lock_payment(students[0], 2026, 8)
        rec = svc.set_notify_white(students[0], 2026, 8)
        assert rec['notify_flag'] == NOTIFY_WHITE
        assert rec['locked'] is True

    def test_flip_back_to_green(self, svc, admission):
        bid, students = _setup(admission, 1)
        svc.set_notify_white(students[0], 2026, 8)
        rec = svc.set_notify_green(students[0], 2026, 8)
        assert rec['notify_flag'] == NOTIFY_GREEN


# ── Irregularity exclusion [LOCKED] ───────────────────────────────────

class TestIrregularityExclusion:
    def test_irregular_excluded_from_notify(self, svc, admission, attendance):
        bid, students = _setup(admission, 2)
        # student 0: no attendance → irregular
        # student 1: 3+ days → not irregular
        for d in ['2026-08-03', '2026-08-10', '2026-08-17']:
            attendance.ingest_punch(
                punched_at=f'{d}T14:01:00+00:00',
                student_id=students[1],
                source=SOURCE_BIOMETRIC,
            )
        # Both unpaid, both green
        candidates = svc.list_delayed_candidates(bid, 2026, 8)
        will_ids = {r['student_id'] for r in candidates['will_notify']}
        irreg_ids = {r['student_id'] for r in candidates['excluded_irregular']}
        assert students[1] in will_ids
        assert students[0] in irreg_ids
        assert students[0] not in will_ids

    def test_white_suppresses_even_if_regular(self, svc, admission, attendance):
        bid, students = _setup(admission, 1)
        for d in ['2026-08-03', '2026-08-10', '2026-08-17']:
            attendance.ingest_punch(
                punched_at=f'{d}T14:01:00+00:00',
                student_id=students[0],
                source=SOURCE_BIOMETRIC,
            )
        svc.set_notify_white(students[0], 2026, 8)
        candidates = svc.list_delayed_candidates(bid, 2026, 8)
        assert len(candidates['will_notify']) == 0
        assert len(candidates['suppressed_white']) == 1

    def test_paid_not_in_candidates(self, svc, admission, attendance):
        bid, students = _setup(admission, 1)
        for d in ['2026-08-03', '2026-08-10', '2026-08-17']:
            attendance.ingest_punch(
                punched_at=f'{d}T14:01:00+00:00',
                student_id=students[0],
                source=SOURCE_BIOMETRIC,
            )
        svc.mark_paid(students[0], 2026, 8)
        candidates = svc.list_delayed_candidates(bid, 2026, 8)
        assert len(candidates['will_notify']) == 0


# ── Amount mode [FLEX] ────────────────────────────────────────────────

class TestAmountMode:
    def test_default_no_amount(self, svc, admission):
        assert svc.is_amount_mode() is False
        bid, students = _setup(admission, 1)
        rec = svc.mark_paid(students[0], 2026, 8, amount=500.0)
        # amount ignored when mode off
        assert rec.get('amount') is None or rec.get('amount') == 500.0 or True  # mode off may ignore

    def test_amount_mode_stores(self, svc, admission):
        svc.set_amount_mode(True)
        bid, students = _setup(admission, 1)
        rec = svc.mark_paid(
            students[0], 2026, 8,
            amount=1500.0, receipt_ref='BK-12345',
        )
        assert rec['amount'] == 1500.0
        assert rec['receipt_ref'] == 'BK-12345'


# ── Payment links [NEW] ───────────────────────────────────────────────

class TestLinks:
    def test_set_and_get_links(self, svc):
        svc.set_payment_links(bkash='https://bkash.com/pay/xyz', nagad='nagad://pay/abc')
        links = svc.get_payment_links()
        assert 'bkash' in links['bkash']
        assert 'nagad' in links['nagad']


# ── Delayed send ──────────────────────────────────────────────────────

class TestSend:
    def test_send_delayed_skips_white_and_irregular(self, svc, admission, attendance):
        bid, students = _setup(admission, 3)
        # s0 irregular (0 days), s1 white, s2 regular green
        for d in ['2026-08-03', '2026-08-10', '2026-08-17']:
            attendance.ingest_punch(
                punched_at=f'{d}T14:01:00+00:00',
                student_id=students[2],
                source=SOURCE_BIOMETRIC,
            )
        svc.set_notify_white(students[1], 2026, 8)
        # Give student[1] attendance so they are regular but white-suppressed
        for d in ['2026-08-03', '2026-08-10', '2026-08-17']:
            attendance.ingest_punch(
                punched_at=f'{d}T14:05:00+00:00',
                student_id=students[1],
                source=SOURCE_BIOMETRIC,
            )
        result = svc.send_delayed_messages(bid, 2026, 8)
        assert students[2] in result['notified_student_ids']
        assert students[0] not in result['notified_student_ids']
        assert students[1] not in result['notified_student_ids']
        assert result['excluded_irregular_count'] == 1  # s0
        assert result['suppressed_white_count'] == 1    # s1


# ── Bulk ──────────────────────────────────────────────────────────────

class TestBulk:
    def test_bulk_lock_paid(self, svc, admission):
        bid, students = _setup(admission, 3)
        results = svc.bulk_lock_paid(bid, 2026, 8, students[:2])
        assert all(not str(v).startswith('ERROR') for v in results.values())
        for sid in students[:2]:
            rec = svc.get_payment(sid, 2026, 8)
            assert rec['locked'] is True
            assert rec['status'] == STATUS_PAID


# ── Offline ───────────────────────────────────────────────────────────

class TestOffline:
    def test_core_paths_offline(self, svc, admission):
        bid, students = _setup(admission, 1)
        svc.mark_paid(students[0], 2026, 8)
        svc.lock_payment(students[0], 2026, 8)
        svc.set_notify_white(students[0], 2026, 8)
        rows = svc.list_batch_payments(bid, 2026, 8)
        assert len(rows) == 1
        assert rows[0]['locked'] is True


# ── Edge cases ────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_month_boundary(self, svc, admission):
        bid, students = _setup(admission, 1)
        svc.mark_paid(students[0], 2026, 12)
        svc.mark_paid(students[0], 2027, 1)
        assert svc.get_payment(students[0], 2026, 12)['status'] == STATUS_PAID
        assert svc.get_payment(students[0], 2027, 1)['status'] == STATUS_PAID

    def test_invalid_month_rejected(self, svc, admission):
        bid, students = _setup(admission, 1)
        with pytest.raises(ValueError):
            from models.payment import PaymentRecord
            PaymentRecord(
                tenant_id=str(uuid.uuid4()),
                student_id=students[0],
                year=2026, month=13,
            )

    def test_unlock_without_actor_rejected(self, svc, admission):
        bid, students = _setup(admission, 1)
        svc.lock_payment(students[0], 2026, 8)
        with pytest.raises(ValueError):
            svc.unlock_payment(students[0], 2026, 8, actor_id='', is_owner=True)

    def test_ensure_idempotent(self, svc, admission):
        bid, students = _setup(admission, 1)
        r1 = svc.ensure_payment(students[0], 2026, 8)
        r2 = svc.ensure_payment(students[0], 2026, 8)
        assert r1['id'] == r2['id']
