"""
Portion 3 tests — Attendance / Irregularity.
Covers every SPEC Module 2 [LOCKED] [BULLET] [FLEX] rule and edge cases.
"""

import pytest
import uuid
from datetime import datetime, date, timedelta, timezone

from models.base import TenantContext, DataAccessLayer
from models.attendance import (
    STATUS_PRESENT, STATUS_LATE, STATUS_ABSENT, STATUS_CROSS_BATCH, STATUS_REVIEW,
    SOURCE_BIOMETRIC, SOURCE_MANUAL,
    FLAG_ANTI_PROXY, FLAG_BIO_MANUAL_CONFLICT,
)
from services.attendance_service import (
    AttendanceService,
    DEFAULT_LATE_THRESHOLD_MINUTES,
    DEFAULT_IRREGULARITY_THRESHOLD_DAYS,
)
from services.admission_service import AdmissionService
from services.audit_service import AuditService
from services.config_service import ConfigService


@pytest.fixture
def ctx():
    return TenantContext(tenant_id=uuid.uuid4(), mode='offline-first')


@pytest.fixture
def layer(ctx):
    return DataAccessLayer(ctx)


@pytest.fixture
def admission(ctx, layer):
    return AdmissionService(
        ctx,
        data_layer=layer,
        audit_service=AuditService(ctx),
        config_service=ConfigService(ctx),
    )


@pytest.fixture
def svc(ctx, layer):
    return AttendanceService(
        ctx,
        data_layer=layer,
        audit_service=AuditService(ctx),
        config_service=ConfigService(ctx),
    )


def _setup_batch_and_students(admission, days=None, hour=14, n_students=3):
    days = days or ['sat', 'mon', 'wed']
    bid = admission.create_batch(days=days, hour=hour)
    students = []
    for i in range(n_students):
        sid, _ = admission.admit_student(
            name=f'Student{i}',
            batch_id=bid,
            student_phone=f'0171000000{i}',
        )
        students.append(sid)
    return bid, students


# ── Config ────────────────────────────────────────────────────────────

class TestConfig:
    def test_default_late_threshold(self, svc):
        assert svc.get_late_threshold() == DEFAULT_LATE_THRESHOLD_MINUTES

    def test_per_batch_late_override(self, svc, admission):
        bid, _ = _setup_batch_and_students(admission, n_students=1)
        svc.set_late_threshold(20, batch_id=bid)
        assert svc.get_late_threshold(bid) == 20
        assert svc.get_late_threshold() == DEFAULT_LATE_THRESHOLD_MINUTES

    def test_irregularity_threshold_shared(self, svc):
        assert svc.get_irregularity_threshold() == DEFAULT_IRREGULARITY_THRESHOLD_DAYS
        svc.set_irregularity_threshold(5)
        assert svc.get_irregularity_threshold() == 5


# ── Device + linking ──────────────────────────────────────────────────

class TestDevice:
    def test_register_and_list(self, svc):
        did = svc.register_device(name='Front Door K60', ip_address='192.168.1.50')
        devices = svc.list_devices()
        assert len(devices) == 1
        assert devices[0]['name'] == 'Front Door K60'
        assert devices[0]['ip_address'] == '192.168.1.50'

    def test_link_device_user(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, n_students=1)
        ok = svc.link_device_user(students[0], '42')
        assert ok
        st = admission.get_student(students[0])
        assert st['biometric_device_user_id'] == '42'


# ── Core evaluation ───────────────────────────────────────────────────

class TestEvaluation:
    def test_present_on_time(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14)
        # Monday 2026-08-17 is a real Monday
        on_date = '2026-08-17'
        svc.ingest_punch(
            punched_at=f'{on_date}T14:05:00+00:00',
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
            device_id='dev1',
        )
        rec = svc.get_attendance(students[0], on_date)
        assert rec['status'] == STATUS_PRESENT
        assert rec['source_precedence'] == SOURCE_BIOMETRIC

    def test_late_after_threshold(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14)
        on_date = '2026-08-17'
        # 14:00 + 12 min = 14:12 → 14:15 is late
        svc.ingest_punch(
            punched_at=f'{on_date}T14:15:00+00:00',
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
        )
        rec = svc.get_attendance(students[0], on_date)
        assert rec['status'] == STATUS_LATE
        assert rec['late_minutes'] == 15

    def test_absent_no_punch(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14)
        on_date = '2026-08-17'
        rid = svc.evaluate_student_day(students[0], on_date)
        rec = svc.get_attendance(students[0], on_date)
        assert rec['status'] == STATUS_ABSENT

    def test_not_scheduled_day_no_absent_obligation(self, svc, admission):
        # Batch only Mon; evaluate a Tuesday
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14)
        on_date = '2026-08-18'  # Tuesday
        svc.evaluate_student_day(students[0], on_date)
        rec = svc.get_attendance(students[0], on_date)
        # Still absent in record, but teacher view filters by scheduled days if needed
        assert rec['status'] == STATUS_ABSENT

    def test_cross_batch_credit(self, svc, admission):
        """Student of batch A punches into batch B on a day that is scheduled for A."""
        # Batch A: Mon 14:00
        bid_a = admission.create_batch(days=['mon'], hour=14, name='A')
        # Batch B: Mon 16:00
        bid_b = admission.create_batch(days=['mon'], hour=16, name='B')
        sid, _ = admission.admit_student(name='Cross', batch_id=bid_a, student_phone='01719999999')
        on_date = '2026-08-17'  # Monday
        # Punch at 16:05 → matches batch B window, own day → cross_batch
        svc.ingest_punch(
            punched_at=f'{on_date}T16:05:00+00:00',
            student_id=sid,
            source=SOURCE_BIOMETRIC,
        )
        rec = svc.get_attendance(sid, on_date)
        assert rec['status'] == STATUS_CROSS_BATCH
        assert rec['credited_batch_id'] == bid_b

    def test_extra_session(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=1)
        # Add extra Wednesday session
        admission.add_extra_session(bid, day='wed', hour=15, expires_on='2026-12-31')
        on_date = '2026-08-19'  # Wednesday
        svc.ingest_punch(
            punched_at=f'{on_date}T15:02:00+00:00',
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
        )
        rec = svc.get_attendance(students[0], on_date)
        assert rec['status'] == STATUS_PRESENT


# ── Biometric vs Manual precedence [LOCKED] ───────────────────────────

class TestPrecedence:
    def test_biometric_authoritative(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=1)
        on_date = '2026-08-17'
        # Biometric present
        svc.ingest_punch(
            punched_at=f'{on_date}T14:03:00+00:00',
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
        )
        # Manual tries to mark absent later — must NOT overwrite
        svc.mark_manual(students[0], on_date, STATUS_ABSENT)
        rec = svc.get_attendance(students[0], on_date)
        assert rec['status'] == STATUS_PRESENT
        assert rec['source_precedence'] == SOURCE_BIOMETRIC

    def test_manual_fills_gap(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=1)
        on_date = '2026-08-17'
        # No biometric — manual present
        rid = svc.mark_manual(students[0], on_date, STATUS_PRESENT)
        rec = svc.get_attendance(students[0], on_date)
        assert rec['status'] == STATUS_PRESENT
        assert rec['source_precedence'] == SOURCE_MANUAL

    def test_bio_manual_conflict_goes_to_review(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=1)
        on_date = '2026-08-17'
        # Biometric late
        svc.ingest_punch(
            punched_at=f'{on_date}T14:20:00+00:00',
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
        )
        # Manual present (different status)
        svc.ingest_punch(
            punched_at=f'{on_date}T14:01:00+00:00',
            student_id=students[0],
            source=SOURCE_MANUAL,
        )
        rec = svc.get_attendance(students[0], on_date)
        assert rec['status'] == STATUS_REVIEW
        assert FLAG_BIO_MANUAL_CONFLICT in rec['flags']
        reviews = svc.list_open_reviews()
        assert any(r['student_id'] == students[0] for r in reviews)


# ── Anti-proxy ────────────────────────────────────────────────────────

class TestAntiProxy:
    def test_rapid_punches_flagged(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=1)
        on_date = '2026-08-17'
        svc.ingest_punch(
            punched_at=f'{on_date}T14:00:00+00:00',
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
            device_id='dev1',
            auto_evaluate=False,
        )
        svc.ingest_punch(
            punched_at=f'{on_date}T14:00:30+00:00',  # 30s later — within 90s window
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
            device_id='dev1',
            auto_evaluate=True,
        )
        rec = svc.get_attendance(students[0], on_date)
        assert rec['status'] == STATUS_REVIEW
        assert FLAG_ANTI_PROXY in rec['flags']


# ── Manual bulk ───────────────────────────────────────────────────────

class TestManualBulk:
    def test_bulk_mark(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=3)
        on_date = '2026-08-17'
        marks = {
            students[0]: STATUS_PRESENT,
            students[1]: STATUS_LATE,
            students[2]: STATUS_ABSENT,
        }
        results = svc.bulk_mark(bid, on_date, marks)
        assert all(not str(v).startswith('ERROR') for v in results.values())
        assert svc.get_attendance(students[0], on_date)['status'] == STATUS_PRESENT
        assert svc.get_attendance(students[1], on_date)['status'] == STATUS_LATE
        assert svc.get_attendance(students[2], on_date)['status'] == STATUS_ABSENT

    def test_manual_time_string(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=1)
        on_date = '2026-08-17'
        svc.mark_manual(students[0], on_date, '14:03')
        rec = svc.get_attendance(students[0], on_date)
        assert rec['status'] == STATUS_PRESENT


# ── Teacher views ─────────────────────────────────────────────────────

class TestTeacherViews:
    def test_absentees(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=3)
        on_date = '2026-08-17'
        # Only student 0 present
        svc.ingest_punch(
            punched_at=f'{on_date}T14:02:00+00:00',
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
        )
        # Force evaluate others
        for s in students[1:]:
            svc.evaluate_student_day(s, on_date)
        abs_list = svc.get_absentees(bid, on_date, days_back=1)
        assert abs_list[0]['count'] == 2
        ids = {a['student_id'] for a in abs_list[0]['absentees']}
        assert students[1] in ids and students[2] in ids

    def test_batch_attendance(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=2)
        on_date = '2026-08-17'
        rows = svc.get_batch_attendance(bid, on_date)
        assert len(rows) == 2


# ── Irregularity ──────────────────────────────────────────────────────

class TestIrregularity:
    def test_count_and_threshold(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon', 'wed', 'fri'], hour=14, n_students=1)
        sid = students[0]
        # Mark present on 2 Mondays in August 2026
        # 2026-08-03, 10, 17, 24, 31 are Mondays
        for d in ['2026-08-03', '2026-08-10']:
            svc.ingest_punch(
                punched_at=f'{d}T14:01:00+00:00',
                student_id=sid,
                source=SOURCE_BIOMETRIC,
            )
        assert svc.count_attended_days(sid, 2026, 8) == 2
        assert svc.is_irregular(sid, 2026, 8, bid) is True  # < 3
        # Add one more
        svc.ingest_punch(
            punched_at='2026-08-17T14:01:00+00:00',
            student_id=sid,
            source=SOURCE_BIOMETRIC,
        )
        assert svc.count_attended_days(sid, 2026, 8) == 3
        assert svc.is_irregular(sid, 2026, 8, bid) is False

    def test_list_irregular(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=2)
        # student 0 gets 1 day, student 1 gets nothing
        svc.ingest_punch(
            punched_at='2026-08-17T14:01:00+00:00',
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
        )
        irreg = svc.list_irregular_students(bid, 2026, 8)
        assert len(irreg) == 2  # both < 3


# ── Review resolution ─────────────────────────────────────────────────

class TestReview:
    def test_resolve_review(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=1)
        on_date = '2026-08-17'
        # Force anti-proxy
        svc.ingest_punch(
            punched_at=f'{on_date}T14:00:00+00:00',
            student_id=students[0], source=SOURCE_BIOMETRIC, device_id='d1',
            auto_evaluate=False,
        )
        svc.ingest_punch(
            punched_at=f'{on_date}T14:00:20+00:00',
            student_id=students[0], source=SOURCE_BIOMETRIC, device_id='d1',
        )
        reviews = svc.list_open_reviews()
        assert len(reviews) >= 1
        fid = reviews[0]['id']
        ok = svc.resolve_review(fid, STATUS_PRESENT, actor_id=str(uuid.uuid4()), notes='Verified OK')
        assert ok
        rec = svc.get_attendance(students[0], on_date)
        assert rec['status'] == STATUS_PRESENT
        assert rec['is_reviewed'] is True
        assert svc.list_open_reviews() == [] or all(
            r['id'] != fid for r in svc.list_open_reviews()
        )


# ── Messaging + irregularity gate ─────────────────────────────────────

class TestNotify:
    def test_evaluate_and_notify_skips_irregular(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=2)
        on_date = '2026-08-17'
        # Both absent; both irregular (0 days)
        summary = svc.evaluate_and_notify(bid, on_date)
        assert len(summary['skipped_irregular']) == 2
        assert len(summary['notified_absence']) == 0
        assert len(summary['teacher_alerts']) == 2

    def test_late_streak_detection(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon', 'tue', 'wed'], hour=14, n_students=1)
        sid = students[0]
        # Three consecutive late days (Mon Tue Wed)
        for d, hour_min in [
            ('2026-08-17', '14:20'),  # Mon
            ('2026-08-18', '14:25'),  # Tue
            ('2026-08-19', '14:30'),  # Wed
        ]:
            svc.ingest_punch(
                punched_at=f'{d}T{hour_min}:00+00:00',
                student_id=sid,
                source=SOURCE_BIOMETRIC,
            )
        streak = svc._late_streak(sid, '2026-08-19')
        assert streak >= 3


# ── Offline / no network assumption ───────────────────────────────────

class TestOffline:
    def test_all_core_paths_work_offline(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=1)
        on_date = '2026-08-17'
        # Ingest, evaluate, mark, bulk, absentees, irregularity — no network
        svc.ingest_punch(
            punched_at=f'{on_date}T14:01:00+00:00',
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
        )
        assert svc.get_attendance(students[0], on_date) is not None
        svc.mark_manual(students[0], on_date, STATUS_PRESENT)  # no-op overwrite blocked
        absentees = svc.get_absentees(bid, on_date)
        assert isinstance(absentees, list)
        assert svc.count_attended_days(students[0], 2026, 8) >= 1


# ── Edge cases ────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_orphan_punch_resolved_on_link(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=1)
        on_date = '2026-08-17'
        # Punch with only device_user_id, no student yet
        svc.ingest_punch(
            punched_at=f'{on_date}T14:02:00+00:00',
            device_user_id='99',
            source=SOURCE_BIOMETRIC,
            device_id='dev1',
            auto_evaluate=False,
        )
        # Link
        svc.link_device_user(students[0], '99')
        # Re-evaluate
        svc.evaluate_student_day(students[0], on_date)
        rec = svc.get_attendance(students[0], on_date)
        assert rec['status'] == STATUS_PRESENT

    def test_per_batch_late_threshold(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=1)
        svc.set_late_threshold(30, batch_id=bid)  # generous
        on_date = '2026-08-17'
        svc.ingest_punch(
            punched_at=f'{on_date}T14:25:00+00:00',  # 25 min late vs global 12, but per-batch 30
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
        )
        rec = svc.get_attendance(students[0], on_date)
        assert rec['status'] == STATUS_PRESENT  # within 30 min

    def test_expired_extra_session_ignored(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=1)
        admission.add_extra_session(bid, day='wed', hour=15, expires_on='2026-01-01')  # expired
        on_date = '2026-08-19'  # Wed
        svc.ingest_punch(
            punched_at=f'{on_date}T15:02:00+00:00',
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
        )
        rec = svc.get_attendance(students[0], on_date)
        # Not scheduled (extra expired) → absent
        assert rec['status'] == STATUS_ABSENT

    def test_idempotent_reevaluate(self, svc, admission):
        bid, students = _setup_batch_and_students(admission, days=['mon'], hour=14, n_students=1)
        on_date = '2026-08-17'
        svc.ingest_punch(
            punched_at=f'{on_date}T14:01:00+00:00',
            student_id=students[0],
            source=SOURCE_BIOMETRIC,
        )
        r1 = svc.get_attendance(students[0], on_date)
        svc.evaluate_student_day(students[0], on_date)
        r2 = svc.get_attendance(students[0], on_date)
        assert r1['id'] == r2['id']
        assert r1['status'] == r2['status']
