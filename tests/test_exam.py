"""
Portion 5 — Exams / Results tests (SPEC Module 4).
Covers templates, exam instances, manual entry, history permanence,
analytics, edge cases, tenant isolation, offline writes.
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
from services.exam_service import ExamService
from models.exam import (
    default_main_exam_sections, ExamTemplate, ExamResult,
    SECTION_MCQ, SECTION_WRITTEN, SECTION_CQ,
)


class ExamTestBase(unittest.TestCase):
    def setUp(self):
        self.tenant = TenantContext(tenant_id=uuid.uuid4(), mode='offline-first')
        self.dl = DataAccessLayer(self.tenant)
        self.cfg = ConfigService(self.tenant)
        self.audit = AuditService(self.tenant)
        self.adm = AdmissionService(self.tenant, self.dl, self.audit, self.cfg)
        self.exam = ExamService(self.tenant, self.dl, self.audit, self.cfg)
        self.batch_id = self.adm.create_batch(['Sat', 'Mon', 'Wed'], 14)
        self.sid1, _ = self.adm.admit_student(
            name='Student One', batch_id=self.batch_id, student_phone='01710000001'
        )
        self.sid2, _ = self.adm.admit_student(
            name='Student Two', batch_id=self.batch_id, student_phone='01710000002'
        )
        self.today = date.today().isoformat()


class TestTemplates(ExamTestBase):
    def test_ensure_default_template(self):
        t = self.exam.ensure_default_template()
        self.assertTrue(t['is_default'])
        self.assertEqual(len(t['sections']), 3)
        keys = {s['key'] for s in t['sections']}
        self.assertEqual(keys, {'mcq', 'written', 'cq'})
        # idempotent
        t2 = self.exam.ensure_default_template()
        self.assertEqual(t['id'], t2['id'])

    def test_default_sections_match_spec(self):
        secs = default_main_exam_sections()
        mcq = next(s for s in secs if s['key'] == 'mcq')
        self.assertEqual(mcq['question_count'], 15)
        self.assertEqual(mcq['duration_minutes'], 9)
        self.assertTrue(mcq['immediate_result'])
        written = next(s for s in secs if s['key'] == 'written')
        self.assertEqual(written['max_marks'], 60)
        self.assertEqual(written['question_count'], 6)
        self.assertEqual(written['duration_minutes'], 18)
        cq = next(s for s in secs if s['key'] == 'cq')
        self.assertEqual(cq['max_marks'], 10)

    def test_create_custom_template(self):
        tid = self.exam.create_template(
            name='HSC Style',
            sections=[{
                'key': 'cq_only',
                'name': 'CQ Paper',
                'section_type': 'cq',
                'max_marks': 100,
                'question_count': 8,
                'duration_minutes': 120,
                'weight': 1.0,
                'immediate_result': False,
            }],
            subject='Physics',
        )
        t = self.exam.get_template(tid)
        self.assertEqual(t['name'], 'HSC Style')
        self.assertEqual(len(t['sections']), 1)

    def test_open_book_template(self):
        tid = self.exam.create_template(name='Open Book Ch1', is_open_book=True)
        t = self.exam.get_template(tid)
        self.assertTrue(t['is_open_book'])
        self.assertEqual(t['sections'][0]['section_type'], 'open_book')

    def test_update_and_deactivate_template(self):
        tid = self.exam.create_template(name='Temp')
        ok = self.exam.update_template(tid, name='Renamed')
        self.assertTrue(ok)
        self.assertEqual(self.exam.get_template(tid)['name'], 'Renamed')
        self.exam.deactivate_template(tid)
        active = self.exam.list_templates(active_only=True)
        self.assertFalse(any(t['id'] == tid for t in active))


class TestExamInstances(ExamTestBase):
    def test_create_from_default_template(self):
        eid = self.exam.create_exam(
            name='Ch1 Main',
            exam_date=self.today,
            batch_id=self.batch_id,
            chapter_or_topic='Chapter 1',
        )
        e = self.exam.get_exam(eid)
        self.assertEqual(e['name'], 'Ch1 Main')
        self.assertEqual(e['chapter_or_topic'], 'Chapter 1')
        self.assertEqual(len(e['sections']), 3)
        self.assertIsNotNone(e['template_id'])

    def test_ad_hoc_exam(self):
        eid = self.exam.create_exam(
            name='Surprise Quiz',
            exam_date=self.today,
            batch_id=self.batch_id,
            is_ad_hoc=True,
            sections=[{
                'key': 'quiz',
                'name': 'Quiz',
                'section_type': 'custom',
                'max_marks': 20,
                'question_count': 10,
                'duration_minutes': 15,
                'weight': 1.0,
                'immediate_result': True,
            }],
        )
        e = self.exam.get_exam(eid)
        self.assertTrue(e['is_ad_hoc'])
        self.assertEqual(e['sections'][0]['max_marks'], 20)

    def test_invalid_date_raises(self):
        with self.assertRaises(ValueError):
            self.exam.create_exam(name='Bad', exam_date='not-a-date')

    def test_list_filter_and_complete(self):
        eid = self.exam.create_exam(
            name='E1', exam_date=self.today, batch_id=self.batch_id,
            chapter_or_topic='T1',
        )
        listed = self.exam.list_exams(batch_id=self.batch_id, chapter_or_topic='T1')
        self.assertEqual(len(listed), 1)
        self.exam.complete_exam(eid)
        self.assertEqual(self.exam.get_exam(eid)['status'], 'completed')


class TestResultEntry(ExamTestBase):
    def _make_exam(self):
        return self.exam.create_exam(
            name='Main',
            exam_date=self.today,
            batch_id=self.batch_id,
            chapter_or_topic='Motion',
        )

    def test_enter_full_result(self):
        eid = self._make_exam()
        r = self.exam.enter_result(
            exam_id=eid,
            student_id=self.sid1,
            section_scores=[
                {'key': 'mcq', 'marks_obtained': 12},
                {'key': 'written', 'marks_obtained': 48},
                {'key': 'cq', 'marks_obtained': 8},
            ],
        )
        self.assertEqual(r['total_obtained'], 68.0)
        self.assertEqual(r['total_max'], 85.0)  # 15+60+10
        self.assertAlmostEqual(r['percentage'], 80.0, places=1)
        self.assertFalse(r['is_absent'])
        self.assertEqual(r['chapter_or_topic'], 'Motion')
        self.assertEqual(r['roll'], self.adm.get_student(self.sid1)['roll'])

    def test_marks_exceed_max_raises(self):
        eid = self._make_exam()
        with self.assertRaises(ValueError):
            self.exam.enter_result(
                exam_id=eid,
                student_id=self.sid1,
                section_scores=[{'key': 'mcq', 'marks_obtained': 20}],  # max 15
            )

    def test_negative_marks_raises(self):
        eid = self._make_exam()
        with self.assertRaises(ValueError):
            self.exam.enter_result(
                exam_id=eid,
                student_id=self.sid1,
                section_scores=[{'key': 'mcq', 'marks_obtained': -1}],
            )

    def test_mark_absent(self):
        eid = self._make_exam()
        r = self.exam.mark_absent(eid, self.sid1)
        self.assertTrue(r['is_absent'])
        self.assertEqual(r['total_obtained'], 0.0)

    def test_upsert_result(self):
        eid = self._make_exam()
        r1 = self.exam.enter_result(
            eid, self.sid1,
            section_scores=[{'key': 'mcq', 'marks_obtained': 10}],
        )
        r2 = self.exam.enter_result(
            eid, self.sid1,
            section_scores=[
                {'key': 'mcq', 'marks_obtained': 14},
                {'key': 'written', 'marks_obtained': 50},
                {'key': 'cq', 'marks_obtained': 9},
            ],
        )
        self.assertEqual(r1['id'], r2['id'])
        self.assertEqual(r2['total_obtained'], 73.0)
        all_r = self.exam.get_exam_results(eid)
        self.assertEqual(len(all_r), 1)

    def test_bulk_entry(self):
        eid = self._make_exam()
        out = self.exam.enter_bulk_results(eid, [
            {
                'student_id': self.sid1,
                'section_scores': [
                    {'key': 'mcq', 'marks_obtained': 11},
                    {'key': 'written', 'marks_obtained': 40},
                    {'key': 'cq', 'marks_obtained': 7},
                ],
            },
            {
                'student_id': self.sid2,
                'is_absent': True,
            },
        ])
        self.assertEqual(len(out), 2)
        results = self.exam.get_exam_results(eid)
        self.assertEqual(len(results), 2)

    def test_student_history_permanent(self):
        eid1 = self.exam.create_exam(
            name='E1', exam_date=self.today, batch_id=self.batch_id,
            chapter_or_topic='Ch1',
        )
        eid2 = self.exam.create_exam(
            name='E2',
            exam_date=(date.today() - timedelta(days=7)).isoformat(),
            batch_id=self.batch_id,
            chapter_or_topic='Ch2',
        )
        self.exam.enter_result(
            eid1, self.sid1,
            section_scores=[{'key': 'mcq', 'marks_obtained': 10}],
        )
        self.exam.enter_result(
            eid2, self.sid1,
            section_scores=[{'key': 'mcq', 'marks_obtained': 8}],
        )
        hist = self.exam.get_student_results(self.sid1)
        self.assertEqual(len(hist), 2)
        by_topic = self.exam.get_student_results(self.sid1, chapter_or_topic='Ch1')
        self.assertEqual(len(by_topic), 1)

    def test_history_survives_roll_migration(self):
        """[BULLET] results never lost on roll/batch change."""
        eid = self._make_exam()
        self.exam.enter_result(
            eid, self.sid1,
            section_scores=[
                {'key': 'mcq', 'marks_obtained': 13},
                {'key': 'written', 'marks_obtained': 55},
                {'key': 'cq', 'marks_obtained': 9},
            ],
        )
        old_roll = self.adm.get_student(self.sid1)['roll']
        bid2 = self.adm.create_batch(['Sun', 'Tue'], 16)
        mig = self.adm.migrate_student_roll_batch(self.sid1, new_batch_id=bid2)
        self.assertEqual(mig.status, 'completed')
        # result still present under same student_id
        hist = self.exam.get_student_results(self.sid1)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]['total_obtained'], 77.0)
        # roll on result should have been rewritten by migration HISTORY_TABLES
        self.assertNotEqual(old_roll, self.adm.get_student(self.sid1)['roll'])


class TestAnalytics(ExamTestBase):
    def _seed_exam_with_results(self):
        eid = self.exam.create_exam(
            name='Analytics Exam',
            exam_date=self.today,
            batch_id=self.batch_id,
            chapter_or_topic='Waves',
        )
        self.exam.complete_exam(eid)
        self.exam.enter_result(eid, self.sid1, section_scores=[
            {'key': 'mcq', 'marks_obtained': 14},
            {'key': 'written', 'marks_obtained': 30},
            {'key': 'cq', 'marks_obtained': 5},
        ])
        self.exam.enter_result(eid, self.sid2, section_scores=[
            {'key': 'mcq', 'marks_obtained': 10},
            {'key': 'written', 'marks_obtained': 50},
            {'key': 'cq', 'marks_obtained': 9},
        ])
        return eid

    def test_exam_summary(self):
        eid = self._seed_exam_with_results()
        s = self.exam.exam_summary(eid)
        self.assertEqual(s['n_present'], 2)
        self.assertIsNotNone(s['mean_percentage'])
        self.assertIn('mcq', s['section_averages'])
        self.assertIn('written', s['section_averages'])

    def test_topic_heatmap(self):
        self._seed_exam_with_results()
        # second topic
        eid2 = self.exam.create_exam(
            name='Optics', exam_date=self.today, batch_id=self.batch_id,
            chapter_or_topic='Optics',
        )
        self.exam.enter_result(eid2, self.sid1, section_scores=[
            {'key': 'mcq', 'marks_obtained': 5},
        ])
        heat = self.exam.topic_heatmap(batch_id=self.batch_id)
        topics = {h['chapter_or_topic'] for h in heat}
        self.assertIn('Waves', topics)
        self.assertIn('Optics', topics)

    def test_mcq_vs_written_gap(self):
        eid = self._seed_exam_with_results()
        gaps = self.exam.mcq_vs_written_gap(exam_id=eid)
        self.assertEqual(len(gaps), 2)
        for g in gaps:
            self.assertIsNotNone(g['mcq_percentage'])
            self.assertIsNotNone(g['written_percentage'])
            self.assertIsNotNone(g['gap'])

    def test_cohort_comparison(self):
        eid = self._seed_exam_with_results()
        c = self.exam.cohort_comparison(eid)
        self.assertEqual(c['n'], 2)
        self.assertEqual(len(c['leaderboard']), 2)
        self.assertEqual(c['leaderboard'][0]['rank'], 1)

    def test_likely_to_struggle_low_score(self):
        eid = self.exam.create_exam(
            name='Hard', exam_date=self.today, batch_id=self.batch_id,
            chapter_or_topic='Hard Topic',
        )
        self.exam.complete_exam(eid)
        self.exam.enter_result(eid, self.sid1, section_scores=[
            {'key': 'mcq', 'marks_obtained': 2},
            {'key': 'written', 'marks_obtained': 5},
            {'key': 'cq', 'marks_obtained': 1},
        ])
        flagged = self.exam.students_likely_to_struggle(
            self.batch_id, low_score_threshold=40.0
        )
        ids = {f['student_id'] for f in flagged}
        self.assertIn(self.sid1, ids)


class TestEdgeCases(ExamTestBase):
    def test_tenant_isolation(self):
        eid = self.exam.create_exam(
            name='Private', exam_date=self.today, batch_id=self.batch_id,
        )
        t2 = TenantContext(tenant_id=uuid.uuid4(), mode='offline-first')
        exam2 = ExamService(t2, DataAccessLayer(t2), AuditService(t2), ConfigService(t2))
        self.assertEqual(len(exam2.list_exams()), 0)
        self.assertIsNone(exam2.get_exam(eid))

    def test_offline_core_write(self):
        self.assertEqual(self.tenant.mode, 'offline-first')
        eid = self.exam.create_exam(
            name='Offline Exam', exam_date=self.today, batch_id=self.batch_id,
        )
        r = self.exam.enter_result(
            eid, self.sid1,
            section_scores=[{'key': 'mcq', 'marks_obtained': 9}],
        )
        self.assertIsNotNone(r['id'])

    def test_unknown_student_raises(self):
        eid = self.exam.create_exam(
            name='X', exam_date=self.today, batch_id=self.batch_id,
        )
        with self.assertRaises(ValueError):
            self.exam.enter_result(
                eid, str(uuid.uuid4()),
                section_scores=[{'key': 'mcq', 'marks_obtained': 1}],
            )

    def test_unknown_exam_raises(self):
        with self.assertRaises(ValueError):
            self.exam.enter_result(
                str(uuid.uuid4()), self.sid1,
                section_scores=[{'key': 'mcq', 'marks_obtained': 1}],
            )

    def test_zero_max_marks_ad_hoc(self):
        eid = self.exam.create_exam(
            name='Free', exam_date=self.today, is_ad_hoc=True,
            sections=[{
                'key': 's', 'name': 'S', 'section_type': 'custom',
                'max_marks': 0, 'question_count': 0, 'duration_minutes': 0,
                'weight': 1.0, 'immediate_result': False,
            }],
        )
        r = self.exam.enter_result(
            eid, self.sid1,
            section_scores=[{'key': 's', 'marks_obtained': 0, 'max_marks': 0}],
        )
        self.assertEqual(r['percentage'], 0.0)


class TestModelValidation(unittest.TestCase):
    def test_exam_result_recompute(self):
        r = ExamResult(
            tenant_id=str(uuid.uuid4()),
            exam_id=str(uuid.uuid4()),
            student_id=str(uuid.uuid4()),
            section_scores=[
                {'key': 'a', 'marks_obtained': 10, 'max_marks': 20},
                {'key': 'b', 'marks_obtained': 15, 'max_marks': 30},
            ],
        )
        self.assertEqual(r.total_obtained, 25.0)
        self.assertEqual(r.total_max, 50.0)
        self.assertEqual(r.percentage, 50.0)

    def test_invalid_section_type_raises(self):
        with self.assertRaises(ValueError):
            ExamTemplate(
                tenant_id=str(uuid.uuid4()),
                name='Bad',
                sections=[{
                    'key': 'x', 'name': 'X', 'section_type': 'invalid_type',
                    'max_marks': 10,
                }],
            )


if __name__ == '__main__':
    unittest.main()
