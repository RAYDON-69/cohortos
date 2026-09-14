"""
Portion 6 — Content / Vault tests (SPEC Module 5).
Resources, access rules, anti-leak, offline cache, live sessions, edge cases.
"""

import unittest
import uuid
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.base import TenantContext, DataAccessLayer
from services.config_service import ConfigService
from services.audit_service import AuditService
from services.admission_service import AdmissionService
from services.payment_service import PaymentService
from services.exam_service import ExamService
from services.content_service import (
    ContentService, AccessDeniedError, ProtectionPermissionError,
)
from models.content import (
    ContentResource, AccessRule, AccessRuleset,
    TYPE_PDF, TYPE_VIDEO_YOUTUBE, TYPE_IMAGE,
    OP_AND, OP_OR,
    RULE_MIN_ATTENDANCE, RULE_PAID_UP, RULE_EXPIRES_ON,
    RULE_ALWAYS_ALLOW, RULE_ALWAYS_DENY, RULE_SAT_LAST_EXAM,
    PROTECT_OWNER_ONLY, PROTECT_RELAXED, PROTECT_OPEN,
)


class ContentTestBase(unittest.TestCase):
    def setUp(self):
        self.tenant = TenantContext(tenant_id=uuid.uuid4(), mode='offline-first')
        self.dl = DataAccessLayer(self.tenant)
        self.cfg = ConfigService(self.tenant)
        self.audit = AuditService(self.tenant)
        self.adm = AdmissionService(self.tenant, self.dl, self.audit, self.cfg)
        self.pay = PaymentService(self.tenant, self.dl, self.audit, self.cfg)
        self.exam = ExamService(self.tenant, self.dl, self.audit, self.cfg)
        self.svc = ContentService(
            self.tenant, self.dl, self.audit, self.cfg,
            payment_service=self.pay,
            exam_service=self.exam,
        )
        self.batch_id = self.adm.create_batch(['Sat', 'Mon', 'Wed'], 14)
        self.sid, _ = self.adm.admit_student(
            name='Vault Student', batch_id=self.batch_id, student_phone='01720000001'
        )
        self.owner = str(uuid.uuid4())
        self.teacher = str(uuid.uuid4())
        self.desk = str(uuid.uuid4())


class TestResourceCRUD(ContentTestBase):
    def test_create_pdf(self):
        rid = self.svc.create_resource(
            title='Chapter 1 Notes',
            resource_type=TYPE_PDF,
            topic='Chapter 1',
            subject='Physics',
            actor_id=self.owner,
        )
        r = self.svc.get_resource(rid)
        self.assertEqual(r['title'], 'Chapter 1 Notes')
        self.assertEqual(r['resource_type'], TYPE_PDF)
        self.assertEqual(r['protection_level'], PROTECT_OWNER_ONLY)
        self.assertTrue(r['watermark'])
        self.assertTrue(r['no_download'])

    def test_create_youtube_with_timestamps(self):
        rid = self.svc.create_resource(
            title='Wave Lecture',
            resource_type=TYPE_VIDEO_YOUTUBE,
            topic='Waves',
            url='https://youtube.com/watch?v=abc',
            youtube_timestamps=[
                {'label': 'Intro', 'seconds': 0},
                {'label': 'Superposition', 'seconds': 320},
            ],
        )
        r = self.svc.get_resource(rid)
        self.assertEqual(len(r['youtube_timestamps']), 2)

    def test_list_by_topic(self):
        self.svc.create_resource(title='A', topic='T1', resource_type=TYPE_PDF)
        self.svc.create_resource(title='B', topic='T2', resource_type=TYPE_IMAGE)
        self.assertEqual(len(self.svc.list_resources(topic='T1')), 1)
        self.assertEqual(len(self.svc.list_resources(topic='T2')), 1)

    def test_update_and_deactivate(self):
        rid = self.svc.create_resource(title='X', topic='T')
        self.svc.update_resource(rid, title='Y')
        self.assertEqual(self.svc.get_resource(rid)['title'], 'Y')
        self.svc.deactivate_resource(rid)
        self.assertEqual(len(self.svc.list_resources(active_only=True)), 0)

    def test_invalid_type_raises(self):
        with self.assertRaises(ValueError):
            ContentResource(
                tenant_id=str(self.tenant.tenant_id),
                title='Bad',
                resource_type='not_a_type',
            )


class TestAccessRules(ContentTestBase):
    def test_no_rules_allows(self):
        rid = self.svc.create_resource(title='Open-ish', topic='T')
        result = self.svc.evaluate_access(rid, self.sid)
        self.assertTrue(result['allowed'])

    def test_always_deny(self):
        rid = self.svc.create_resource(title='Denied', topic='T')
        self.svc.set_access_rules(rid, OP_AND, [
            {'kind': RULE_ALWAYS_DENY},
        ])
        result = self.svc.evaluate_access(rid, self.sid)
        self.assertFalse(result['allowed'])
        self.assertIn('always_deny', result['reasons'])

    def test_expires_on(self):
        rid = self.svc.create_resource(title='Expired', topic='T')
        past = (date.today() - timedelta(days=1)).isoformat()
        self.svc.set_access_rules(rid, OP_AND, [
            {'kind': RULE_EXPIRES_ON, 'value': past},
        ])
        result = self.svc.evaluate_access(rid, self.sid)
        self.assertFalse(result['allowed'])

        future = (date.today() + timedelta(days=30)).isoformat()
        self.svc.set_access_rules(rid, OP_AND, [
            {'kind': RULE_EXPIRES_ON, 'value': future},
        ])
        result = self.svc.evaluate_access(rid, self.sid)
        self.assertTrue(result['allowed'])

    def test_paid_up_rule(self):
        rid = self.svc.create_resource(title='Paid only', topic='T')
        self.svc.set_access_rules(rid, OP_AND, [
            {'kind': RULE_PAID_UP},
        ])
        # not paid yet
        result = self.svc.evaluate_access(rid, self.sid)
        self.assertFalse(result['allowed'])
        # mark paid
        today = date.today()
        self.pay.mark_paid(self.sid, today.year, today.month)
        result = self.svc.evaluate_access(rid, self.sid)
        self.assertTrue(result['allowed'])

    def test_and_or_composition(self):
        rid = self.svc.create_resource(title='Combo', topic='T')
        # OR: always_deny OR always_allow → allow
        self.svc.set_access_rules(rid, OP_OR, [
            {'kind': RULE_ALWAYS_DENY},
            {'kind': RULE_ALWAYS_ALLOW},
        ])
        self.assertTrue(self.svc.evaluate_access(rid, self.sid)['allowed'])
        # AND: always_deny AND always_allow → deny
        self.svc.set_access_rules(rid, OP_AND, [
            {'kind': RULE_ALWAYS_DENY},
            {'kind': RULE_ALWAYS_ALLOW},
        ])
        self.assertFalse(self.svc.evaluate_access(rid, self.sid)['allowed'])

    def test_sat_last_exam(self):
        rid = self.svc.create_resource(title='Exam gated', topic='T')
        self.svc.set_access_rules(rid, OP_AND, [
            {'kind': RULE_SAT_LAST_EXAM},
        ])
        # no exams yet
        self.assertFalse(self.svc.evaluate_access(rid, self.sid)['allowed'])
        # create exam + result
        eid = self.exam.create_exam(
            name='Gate Exam', exam_date=date.today().isoformat(),
            batch_id=self.batch_id, chapter_or_topic='T',
        )
        self.exam.enter_result(eid, self.sid, section_scores=[
            {'key': 'mcq', 'marks_obtained': 10},
        ])
        self.assertTrue(self.svc.evaluate_access(rid, self.sid)['allowed'])


class TestAntiLeak(ContentTestBase):
    def test_default_owner_only(self):
        rid = self.svc.create_resource(title='Protected', topic='T')
        r = self.svc.get_resource(rid)
        self.assertEqual(r['protection_level'], PROTECT_OWNER_ONLY)
        self.assertTrue(r['is_protection_relaxed'] is False or r.get('is_protection_relaxed') is False)

    def test_teacher_can_relax(self):
        rid = self.svc.create_resource(title='P', topic='T', actor_id=self.owner)
        new = self.svc.relax_protection(rid, actor_id=self.teacher, actor_role='teacher')
        self.assertEqual(new['protection_level'], PROTECT_RELAXED)
        self.assertEqual(new['protection_relaxed_by'], self.teacher)
        self.assertFalse(new['watermark'])
        self.assertFalse(new['no_download'])

    def test_desk_cannot_relax(self):
        rid = self.svc.create_resource(title='P', topic='T')
        with self.assertRaises(ProtectionPermissionError):
            self.svc.relax_protection(rid, actor_id=self.desk, actor_role='desk')

    def test_desk_cannot_set_anti_leak_on_create(self):
        with self.assertRaises(ProtectionPermissionError):
            self.svc.create_resource(
                title='Hack',
                protection_level=PROTECT_RELAXED,
                actor_role='desk',
            )

    def test_desk_cannot_update_anti_leak(self):
        rid = self.svc.create_resource(title='P', topic='T')
        with self.assertRaises(ProtectionPermissionError):
            self.svc.update_resource(
                rid, actor_role='desk', watermark=False,
            )

    def test_viewer_token_lifecycle(self):
        rid = self.svc.create_resource(title='P', topic='T')
        tok = self.svc.issue_viewer_token(rid, self.sid, ttl_minutes=60)
        self.assertTrue(tok['token'])
        self.assertTrue(self.svc.validate_viewer_token(tok['token'], rid, self.sid))
        self.svc.revoke_viewer_token(tok['token'])
        self.assertFalse(self.svc.validate_viewer_token(tok['token'], rid, self.sid))

    def test_restore_protection(self):
        rid = self.svc.create_resource(title='P', topic='T')
        self.svc.relax_protection(rid, actor_id=self.teacher, actor_role='teacher')
        self.svc.restore_protection(rid, actor_id=self.owner, actor_role='owner')
        r = self.svc.get_resource(rid)
        self.assertEqual(r['protection_level'], PROTECT_OWNER_ONLY)
        self.assertTrue(r['watermark'])


class TestOfflineCache(ContentTestBase):
    def test_mark_for_offline_allowed(self):
        rid = self.svc.create_resource(title='Cacheable', topic='T')
        entry = self.svc.mark_for_offline(self.sid, rid, local_path='/local/x.pdf')
        self.assertEqual(entry['resource_id'], rid)
        self.assertTrue(entry['last_access_allowed'])
        self.assertEqual(len(self.svc.list_offline_cache(self.sid)), 1)

    def test_mark_denied_raises(self):
        rid = self.svc.create_resource(title='No', topic='T')
        self.svc.set_access_rules(rid, OP_AND, [{'kind': RULE_ALWAYS_DENY}])
        with self.assertRaises(AccessDeniedError):
            self.svc.mark_for_offline(self.sid, rid)

    def test_recheck_on_reconnect(self):
        rid = self.svc.create_resource(title='C', topic='T')
        self.svc.mark_for_offline(self.sid, rid)
        # tighten rules
        self.svc.set_access_rules(rid, OP_AND, [{'kind': RULE_ALWAYS_DENY}])
        results = self.svc.recheck_offline_access(self.sid)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]['allowed'])
        cache = self.svc.list_offline_cache(self.sid)[0]
        self.assertFalse(cache['last_access_allowed'])


class TestChunkedUpload(ContentTestBase):
    def test_chunk_progress(self):
        rid = self.svc.create_resource(
            title='Big PDF', topic='T', total_chunks=10, file_size_bytes=50_000_000,
        )
        r = self.svc.register_chunk_progress(rid, uploaded_chunks=4, checksum='abc')
        self.assertEqual(r['uploaded_chunks'], 4)
        self.assertFalse(r['upload_complete'])
        r = self.svc.register_chunk_progress(rid, uploaded_chunks=10)
        self.assertTrue(r['upload_complete'])

    def test_chunk_overflow_raises(self):
        rid = self.svc.create_resource(title='B', topic='T', total_chunks=5)
        with self.assertRaises(ValueError):
            self.svc.register_chunk_progress(rid, uploaded_chunks=6)


class TestLiveSession(ContentTestBase):
    def test_lifecycle(self):
        sid = self.svc.create_live_session(
            title='Evening Class', batch_id=self.batch_id, host_id=self.teacher,
        )
        sess = self.svc.get_live_session(sid)
        self.assertEqual(sess['status'], 'scheduled')
        self.svc.start_live_session(sid)
        self.assertEqual(self.svc.get_live_session(sid)['status'], 'live')
        self.svc.raise_hand(sid, self.sid)
        self.assertIn(self.sid, self.svc.get_live_session(sid)['hand_raises'])
        self.svc.lower_hand(sid, self.sid)
        self.assertNotIn(self.sid, self.svc.get_live_session(sid)['hand_raises'])
        self.svc.add_poll(sid, 'Clear?', ['Yes', 'No'])
        self.assertEqual(len(self.svc.get_live_session(sid)['polls']), 1)
        self.svc.end_live_session(sid)
        self.assertEqual(self.svc.get_live_session(sid)['status'], 'ended')


class TestEdgeCases(ContentTestBase):
    def test_tenant_isolation(self):
        rid = self.svc.create_resource(title='Private', topic='T')
        t2 = TenantContext(tenant_id=uuid.uuid4(), mode='offline-first')
        svc2 = ContentService(t2, DataAccessLayer(t2))
        self.assertEqual(len(svc2.list_resources()), 0)
        self.assertIsNone(svc2.get_resource(rid))

    def test_offline_core_write(self):
        self.assertEqual(self.tenant.mode, 'offline-first')
        rid = self.svc.create_resource(title='Offline', topic='T')
        self.assertIsNotNone(rid)

    def test_suggest_videos_stub(self):
        self.assertEqual(self.svc.suggest_videos('Waves'), [])

    def test_batch_scoped_list(self):
        self.svc.create_resource(
            title='Batch A', topic='T', batch_ids=[self.batch_id],
        )
        other_batch = self.adm.create_batch(['Sun'], 10)
        self.svc.create_resource(
            title='Batch B', topic='T', batch_ids=[other_batch],
        )
        listed = self.svc.list_resources(batch_id=self.batch_id)
        titles = {r['title'] for r in listed}
        self.assertIn('Batch A', titles)
        self.assertNotIn('Batch B', titles)


class TestModelValidation(unittest.TestCase):
    def test_access_rule_invalid_kind(self):
        with self.assertRaises(ValueError):
            AccessRule(kind='not_a_rule')

    def test_ruleset_operator(self):
        with self.assertRaises(ValueError):
            AccessRuleset(operator='XOR')


if __name__ == '__main__':
    unittest.main()
