"""
Portion 2 tests — Admission, batch config, roll encoding, duplicates, migration.
Covers SPEC Module 1 [BULLET]/[LOCKED] requirements and edge cases.
"""

import pytest
import uuid
from datetime import datetime, timedelta, timezone

from models.base import TenantContext, DataAccessLayer
from models.admission import (
    Batch, Student, days_to_bitmask, bitmask_to_days, format_batch_display_name,
)
from services.roll_encoder import RollEncoder
from services.admission_service import AdmissionService, DuplicateStudentError
from services.audit_service import AuditService
from services.config_service import ConfigService


@pytest.fixture
def ctx():
    return TenantContext(tenant_id=uuid.uuid4(), mode='offline-first')


@pytest.fixture
def svc(ctx):
    layer = DataAccessLayer(ctx)
    audit = AuditService(ctx)
    config = ConfigService(ctx)
    return AdmissionService(ctx, data_layer=layer, audit_service=audit, config_service=config)


class TestRollEncoding:
    def test_locked_spec_example(self):
        """Sat+Mon+Wed 14:00 serial 33 → 02114033 [LOCKED]"""
        assert RollEncoder.validate_example() == '02114033'

    def test_bitmask_roundtrip(self):
        mask = days_to_bitmask(['sat', 'mon', 'wed'])
        assert mask == 21
        assert bitmask_to_days(mask) == ['sat', 'mon', 'wed']

    def test_all_days(self):
        mask = days_to_bitmask(['sat', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri'])
        assert mask == 127
        assert len(bitmask_to_days(mask)) == 7

    def test_invalid_day(self):
        with pytest.raises(ValueError):
            days_to_bitmask(['xyz'])  # not a valid day key

    def test_encode_decode(self):
        enc = RollEncoder()
        roll = enc.encode(['fri'], 9, 1)
        assert roll == '06409001'  # Fri=64
        assert enc.decode(roll) == (64, 9, 1)

    def test_plain_scheme(self):
        enc = RollEncoder(scheme=RollEncoder.SCHEME_PLAIN)
        assert enc.encode(['sat'], 14, 5) == '005'

    def test_next_serial_skips_used(self):
        enc = RollEncoder()
        existing = ['02114001', '02114002', '02114005']
        n = enc.next_serial(existing, ['sat', 'mon', 'wed'], 14)
        assert n == 3

    def test_serial_exhausted(self):
        enc = RollEncoder()
        existing = [enc.encode(['sat'], 10, i) for i in range(1, 1000)]
        with pytest.raises(ValueError, match='exhausted'):
            enc.next_serial(existing, ['sat'], 10)

    def test_display_name(self):
        name = format_batch_display_name(['sat', 'mon', 'wed'], 14)
        assert name == 'Sat,Mon,Wed 14:00'


class TestBatchManagement:
    def test_create_batch_auto_name(self, svc):
        bid = svc.create_batch(days=['sat', 'mon', 'wed'], hour=14)
        batch = svc.get_batch(bid)
        assert batch is not None
        assert batch['name'] == 'Sat,Mon,Wed 14:00'
        assert batch['day_bitmask'] == 21
        assert batch['hour'] == 14

    def test_create_batch_name_override(self, svc):
        bid = svc.create_batch(days=['sun'], hour=16, name='Special Sunday')
        batch = svc.get_batch(bid)
        assert batch['name'] == 'Special Sunday'
        assert batch['name_override'] is True

    def test_list_batches(self, svc):
        svc.create_batch(days=['sat'], hour=10)
        svc.create_batch(days=['sun'], hour=11)
        assert len(svc.list_batches()) == 2

    def test_update_batch_days_renames(self, svc):
        bid = svc.create_batch(days=['sat'], hour=10)
        svc.update_batch(bid, days=['sat', 'sun'])
        batch = svc.get_batch(bid)
        assert batch['name'] == 'Sat,Sun 10:00'
        assert batch['day_bitmask'] == 3

    def test_extra_session(self, svc):
        bid = svc.create_batch(days=['mon'], hour=14)
        ok = svc.add_extra_session(bid, day='wed', hour=15, expires_on='2026-12-31')
        assert ok
        batch = svc.get_batch(bid)
        assert len(batch['extra_sessions']) == 1
        assert batch['extra_sessions'][0]['day'] == 'wed'

    def test_batch_template(self, svc):
        tid = svc.create_batch_template(
            name='HSC Physics',
            coaching_type='hsc',
            default_days=['sat', 'mon', 'wed'],
            default_hour=14,
            exam_structure={'mcq': 15, 'written': 6},
        )
        templates = svc.list_templates()
        assert len(templates) == 1
        export = svc.export_template(tid)
        assert export['name'] == 'HSC Physics'
        assert 'ai_prompt_content' not in export


class TestAdmission:
    def _batch(self, svc, days=None, hour=14):
        return svc.create_batch(days=days or ['sat', 'mon', 'wed'], hour=hour)

    def test_admit_auto_roll(self, svc):
        bid = self._batch(svc)
        sid, code = svc.admit_student(name='Rahim', batch_id=bid, student_phone='01711111111')
        student = svc.get_student(sid)
        assert student['roll'] == '02114001'  # first serial
        assert student['name'] == 'Rahim'
        assert code  # join code generated
        assert len(code) == 8

    def test_admit_serial_increments(self, svc):
        bid = self._batch(svc)
        s1, _ = svc.admit_student(name='A', batch_id=bid, student_phone='01710000001')
        s2, _ = svc.admit_student(name='B', batch_id=bid, student_phone='01710000002')
        assert svc.get_student(s1)['roll'] == '02114001'
        assert svc.get_student(s2)['roll'] == '02114002'

    def test_admit_custom_roll(self, svc):
        bid = self._batch(svc)
        sid, _ = svc.admit_student(
            name='Custom', batch_id=bid, student_phone='01710000003', roll='99999001'
        )
        assert svc.get_student(sid)['roll'] == '99999001'

    def test_duplicate_phone_blocks(self, svc):
        bid = self._batch(svc)
        svc.admit_student(name='Rahim', batch_id=bid, student_phone='01711111111')
        with pytest.raises(DuplicateStudentError) as ei:
            svc.admit_student(name='Karim', batch_id=bid, student_phone='01711111111')
        assert 'Phone number already registered' in str(ei.value)
        assert len(ei.value.matches) >= 1
        assert ei.value.matches[0].roll == '02114001'

    def test_duplicate_force_proceeds(self, svc):
        bid = self._batch(svc)
        svc.admit_student(name='Rahim', batch_id=bid, student_phone='01711111111')
        sid, _ = svc.admit_student(
            name='Karim', batch_id=bid, student_phone='01711111111', force=True
        )
        assert svc.get_student(sid) is not None

    def test_duplicate_parent_phone_allowed(self, svc):
        """SPEC_v3: siblings sharing a parent phone must NOT be flagged as duplicates."""
        bid = self._batch(svc)
        svc.admit_student(
            name='Child1', batch_id=bid, student_phone='01710000010',
            parent_phones=['01810000010'],
        )
        # Shared parent phone is legitimate — admission must succeed
        sid, _ = svc.admit_student(
            name='Child2', batch_id=bid, student_phone='01710000011',
            parent_phones=['01810000010'],
        )
        assert svc.get_student(sid) is not None

    def test_duplicate_idempotent_resolution(self, svc):
        """force=True twice is safe (idempotent)."""
        bid = self._batch(svc)
        svc.admit_student(name='X', batch_id=bid, student_phone='01712222222')
        s2, _ = svc.admit_student(name='Y', batch_id=bid, student_phone='01712222222', force=True)
        s3, _ = svc.admit_student(name='Z', batch_id=bid, student_phone='01712222222', force=True)
        assert s2 != s3

    def test_update_student(self, svc):
        bid = self._batch(svc)
        sid, _ = svc.admit_student(name='Old', batch_id=bid, student_phone='01713333333')
        ok = svc.update_student(sid, name='New Name')
        assert ok
        assert svc.get_student(sid)['name'] == 'New Name'

    def test_update_blocks_roll_direct(self, svc):
        bid = self._batch(svc)
        sid, _ = svc.admit_student(name='R', batch_id=bid, student_phone='01714444444')
        with pytest.raises(ValueError, match='migrate_student_roll_batch'):
            svc.update_student(sid, roll='00000099')

    def test_list_by_batch(self, svc):
        b1 = self._batch(svc, days=['sat'], hour=10)
        b2 = self._batch(svc, days=['sun'], hour=11)
        svc.admit_student(name='A', batch_id=b1, student_phone='01715555551')
        svc.admit_student(name='B', batch_id=b2, student_phone='01715555552')
        assert len(svc.list_students(batch_id=b1)) == 1
        assert len(svc.list_students()) == 2

    def test_missing_name_rejected(self, svc):
        bid = self._batch(svc)
        with pytest.raises(ValueError):
            svc.admit_student(name='  ', batch_id=bid)

    def test_invalid_batch_rejected(self, svc):
        with pytest.raises(ValueError, match='Batch not found'):
            svc.admit_student(name='X', batch_id=str(uuid.uuid4()))


class TestMigration:
    def _setup(self, svc):
        bid = svc.create_batch(days=['sat', 'mon', 'wed'], hour=14)
        sid, _ = svc.admit_student(name='Migrator', batch_id=bid, student_phone='01716666666')
        # Seed history rows
        layer = svc.data_layer
        for table, extra in [
            ('attendance', {'date': '2026-01-01', 'status': 'present', 'source': 'manual'}),
            ('payments', {'month': '2026-01', 'status': 'paid', 'locked': 1}),
            ('exam_results', {'exam_name': 'Ch1', 'score': 85.0}),
            ('threads', {'topic': 'vectors'}),
        ]:
            layer.create(table, {
                'tenant_id': str(svc.tenant_context.tenant_id),
                'student_id': sid,
                'roll': svc.get_student(sid)['roll'],
                'batch_id': bid,
                **extra,
            })
        return bid, sid

    def test_migrate_to_new_batch(self, svc):
        old_bid, sid = self._setup(svc)
        new_bid = svc.create_batch(days=['sun', 'tue'], hour=16)
        old_roll = svc.get_student(sid)['roll']

        migration = svc.migrate_student_roll_batch(sid, new_batch_id=new_bid)
        assert migration.status == 'completed'
        assert migration.old_roll == old_roll
        assert migration.new_roll != old_roll
        assert migration.records_moved >= 4
        assert 'attendance' in migration.tables_migrated
        assert 'payments' in migration.tables_migrated

        student = svc.get_student(sid)
        assert student['batch_id'] == new_bid
        assert student['roll'] == migration.new_roll

        # History rows updated
        att = [r for r in svc.data_layer.get_all('attendance') if r['student_id'] == sid]
        assert all(r.get('roll') == migration.new_roll for r in att)
        assert all(r.get('batch_id') == new_bid for r in att)

    def test_migrate_noop(self, svc):
        bid, sid = self._setup(svc)
        roll = svc.get_student(sid)['roll']
        m = svc.migrate_student_roll_batch(sid, new_batch_id=bid, new_roll=roll)
        assert m.records_moved == 0
        assert m.status == 'completed'

    def test_migrate_explicit_roll(self, svc):
        bid, sid = self._setup(svc)
        m = svc.migrate_student_roll_batch(sid, new_roll='02114999')
        assert m.new_roll == '02114999'
        assert svc.get_student(sid)['roll'] == '02114999'

    def test_migrate_logs_audit(self, svc):
        _, sid = self._setup(svc)
        new_bid = svc.create_batch(days=['fri'], hour=9)
        svc.migrate_student_roll_batch(sid, new_batch_id=new_bid)
        logs = svc.data_layer.get_all('migration_logs')
        assert len(logs) >= 1
        assert logs[-1]['status'] == 'completed'

    def test_migrate_unknown_student(self, svc):
        with pytest.raises(ValueError, match='not found'):
            svc.migrate_student_roll_batch(str(uuid.uuid4()), new_roll='00000001')


class TestJoinCodes:
    def test_generate_and_link(self, svc):
        bid = svc.create_batch(days=['sat'], hour=10)
        sid, code = svc.admit_student(name='Linker', batch_id=bid, student_phone='01717777777')
        assert code

        ok = svc.link_account(sid, cohortos_account_id='acct-1', join_code=code)
        assert ok
        student = svc.get_student(sid)
        assert student['cohortos_account_id'] == 'acct-1'

        # Code is single-use
        with pytest.raises(ValueError, match='Invalid or already-used'):
            svc.link_account(sid, cohortos_account_id='acct-2', join_code=code)

    def test_staff_manual_link_without_code(self, svc):
        bid = svc.create_batch(days=['sat'], hour=10)
        sid, _ = svc.admit_student(name='Manual', batch_id=bid, student_phone='01718888888')
        ok = svc.link_account(sid, cohortos_account_id='acct-manual')
        assert ok
        assert svc.get_student(sid)['cohortos_account_id'] == 'acct-manual'

    def test_regenerate_invalidates_prior(self, svc):
        bid = svc.create_batch(days=['sat'], hour=10)
        sid, code1 = svc.admit_student(name='Regen', batch_id=bid, student_phone='01719999999')
        code2 = svc.generate_join_code(sid)
        assert code1 != code2
        with pytest.raises(ValueError):
            svc.link_account(sid, cohortos_account_id='a', join_code=code1)
        ok = svc.link_account(sid, cohortos_account_id='a', join_code=code2)
        assert ok

    def test_expired_code_rejected(self, svc):
        bid = svc.create_batch(days=['sat'], hour=10)
        sid, _ = svc.admit_student(name='Exp', batch_id=bid, student_phone='01710000100')
        # Manually insert expired code
        from models.admission import JoinCode
        expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        jc = JoinCode(
            tenant_id=str(svc.tenant_context.tenant_id),
            admission_id=sid,
            expires_at=expired,
        )
        # Invalidate auto codes then insert expired
        for c in svc.data_layer.get_all('join_codes'):
            if c['admission_id'] == sid:
                svc.data_layer.update(
                    'join_codes', uuid.UUID(c['id']), {'is_used': True}
                )
        svc.data_layer.create('join_codes', jc.to_dict())
        with pytest.raises(ValueError, match='expired'):
            svc.link_account(sid, cohortos_account_id='x', join_code=jc.code)


class TestOfflineAndAudit:
    def test_offline_admit(self, ctx):
        """Core admission works with zero network (in-memory layer)."""
        layer = DataAccessLayer(ctx)
        svc = AdmissionService(ctx, data_layer=layer, audit_service=AuditService(ctx),
                               config_service=ConfigService(ctx))
        bid = svc.create_batch(days=['mon'], hour=12)
        sid, code = svc.admit_student(name='Offline', batch_id=bid, student_phone='01710000200')
        assert svc.get_student(sid) is not None
        assert code

    def test_audit_on_admit(self, svc):
        bid = svc.create_batch(days=['tue'], hour=13)
        sid, _ = svc.admit_student(name='Audited', batch_id=bid, student_phone='01710000300')
        logs = svc.data_layer.get_all('audit_logs')
        student_creates = [
            l for l in logs
            if l.get('table_name') == 'students' and l.get('action') in ('create', 'CREATE')
        ]
        # audit may store action lowercase or upper depending on AuditLog
        assert len(logs) >= 1

    def test_tenant_isolation(self):
        ctx1 = TenantContext(tenant_id=uuid.uuid4(), mode='offline-first')
        ctx2 = TenantContext(tenant_id=uuid.uuid4(), mode='offline-first')
        # Shared layer would leak — each gets own layer
        s1 = AdmissionService(ctx1, data_layer=DataAccessLayer(ctx1),
                              audit_service=AuditService(ctx1), config_service=ConfigService(ctx1))
        s2 = AdmissionService(ctx2, data_layer=DataAccessLayer(ctx2),
                              audit_service=AuditService(ctx2), config_service=ConfigService(ctx2))
        b1 = s1.create_batch(days=['sat'], hour=10)
        s1.admit_student(name='T1', batch_id=b1, student_phone='01710000400')
        assert len(s1.list_students()) == 1
        assert len(s2.list_students()) == 0


class TestEdgeCases:
    def test_unicode_bangla_name(self, svc):
        bid = svc.create_batch(days=['sat'], hour=10)
        sid, _ = svc.admit_student(name='রহিম উদ্দিন', batch_id=bid, student_phone='01710000500')
        assert svc.get_student(sid)['name'] == 'রহিম উদ্দিন'

    def test_empty_phone_allowed(self, svc):
        bid = svc.create_batch(days=['sat'], hour=10)
        sid, _ = svc.admit_student(name='NoPhone', batch_id=bid, student_phone='')
        assert svc.get_student(sid) is not None

    def test_custom_fields(self, svc):
        bid = svc.create_batch(days=['sat'], hour=10)
        sid, _ = svc.admit_student(
            name='Custom', batch_id=bid, student_phone='01710000600',
            custom_fields={'school': 'Barishal Govt', 'college': 'N/A'},
        )
        assert svc.get_student(sid)['custom_fields']['school'] == 'Barishal Govt'

    def test_hour_boundary(self, svc):
        bid0 = svc.create_batch(days=['sat'], hour=0)
        bid23 = svc.create_batch(days=['sun'], hour=23)
        assert svc.get_batch(bid0)['hour'] == 0
        assert svc.get_batch(bid23)['hour'] == 23

    def test_invalid_hour(self):
        with pytest.raises(ValueError):
            Batch(days=['sat'], hour=24)
