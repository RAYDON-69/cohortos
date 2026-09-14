"""
Exam / Results service — SPEC Module 4.

- Flexible templates (default main-exam + custom + open-book)
- Exam instances (template-based or ad-hoc)
- Manual score entry only
- Permanent results (never lost on roll/batch change)
- Batch-level analytics: section averages, MCQ-vs-written gap,
  cohort stats, simple “likely to struggle” signal
- Offline-first, tenant-scoped, audit-logged, sync-ready
"""

from __future__ import annotations

from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional, Tuple
import uuid
import copy
import statistics

from models.base import TenantContext, DataAccessLayer
from models.exam import (
    ExamTemplate, Exam, ExamResult,
    default_main_exam_sections,
    SECTION_MCQ, SECTION_WRITTEN, SECTION_CQ, SECTION_OPEN_BOOK,
    EXAM_DRAFT, EXAM_SCHEDULED, EXAM_COMPLETED, EXAM_CANCELLED,
    _utcnow,
)
from services.audit_service import AuditService
from services.config_service import ConfigService


class ExamService:
    """Offline-first exam & results engine."""

    def __init__(
        self,
        tenant_context: TenantContext,
        data_layer: Optional[DataAccessLayer] = None,
        audit_service: Optional[AuditService] = None,
        config_service: Optional[ConfigService] = None,
        attendance_service=None,
        sync_engine=None,
    ):
        self.tenant_context = tenant_context
        self.data_layer = data_layer or DataAccessLayer(tenant_context)
        self.audit_service = audit_service or AuditService(tenant_context)
        self.config_service = config_service or ConfigService(tenant_context)
        self.attendance_service = attendance_service
        self.sync_engine = sync_engine

    # ── Templates ─────────────────────────────────────────────────────

    def ensure_default_template(self, actor_id: Optional[str] = None) -> Dict[str, Any]:
        """Create the SPEC default main-exam template if none exists."""
        existing = [
            t for t in self.data_layer.get_all('exam_templates')
            if t.get('is_default') and t.get('is_active', True)
        ]
        if existing:
            return existing[0]
        tpl = ExamTemplate(
            tenant_id=str(self.tenant_context.tenant_id),
            name='Main Exam (default)',
            description='15 MCQ + 6 Physics Maths + 1 CQ — origin client structure',
            is_default=True,
            is_open_book=False,
            sections=default_main_exam_sections(),
        )
        return self._create_template(tpl, actor_id)

    def create_template(
        self,
        name: str,
        sections: Optional[List[Dict[str, Any]]] = None,
        description: str = '',
        subject: str = '',
        is_open_book: bool = False,
        is_default: bool = False,
        actor_id: Optional[str] = None,
    ) -> str:
        tpl = ExamTemplate(
            tenant_id=str(self.tenant_context.tenant_id),
            name=name,
            description=description,
            subject=subject,
            is_open_book=is_open_book,
            is_default=is_default,
            sections=sections or (default_main_exam_sections() if not is_open_book else None),
        )
        stored = self._create_template(tpl, actor_id)
        return stored['id']

    def _create_template(self, tpl: ExamTemplate, actor_id: Optional[str]) -> Dict[str, Any]:
        rid = self.data_layer.create('exam_templates', tpl.to_dict())
        stored = self.data_layer.get('exam_templates', rid)
        self.audit_service.log_create(
            table_name='exam_templates',
            record_id=rid,
            new_state=stored or tpl.to_dict(),
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._persist_audit()
        self._queue_sync('create', 'exam_templates', str(rid), None, stored)
        return stored or tpl.to_dict()

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        return self.data_layer.get('exam_templates', uuid.UUID(template_id))

    def list_templates(self, active_only: bool = True) -> List[Dict[str, Any]]:
        rows = self.data_layer.get_all('exam_templates')
        if active_only:
            rows = [r for r in rows if r.get('is_active', True)]
        return rows

    def update_template(
        self,
        template_id: str,
        actor_id: Optional[str] = None,
        **kwargs,
    ) -> bool:
        old = self.get_template(template_id)
        if not old:
            return False
        updates = {k: v for k, v in kwargs.items() if k in (
            'name', 'description', 'subject', 'sections', 'is_active',
            'is_default', 'is_open_book',
        )}
        updates['updated_at'] = _utcnow()
        ok = self.data_layer.update('exam_templates', uuid.UUID(template_id), updates)
        if ok:
            new = self.get_template(template_id)
            self.audit_service.log_update(
                table_name='exam_templates',
                record_id=uuid.UUID(template_id),
                old_state=old,
                new_state=new or updates,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._persist_audit()
            self._queue_sync('update', 'exam_templates', template_id, old, new)
        return ok

    def deactivate_template(self, template_id: str, actor_id: Optional[str] = None) -> bool:
        return self.update_template(template_id, actor_id=actor_id, is_active=False)

    # ── Exam instances ────────────────────────────────────────────────

    def create_exam(
        self,
        name: str,
        exam_date: str,
        batch_id: str = '',
        template_id: Optional[str] = None,
        chapter_or_topic: str = '',
        subject: str = '',
        sections: Optional[List[Dict[str, Any]]] = None,
        is_ad_hoc: bool = False,
        notes: str = '',
        status: str = EXAM_SCHEDULED,
        actor_id: Optional[str] = None,
    ) -> str:
        """
        Create an exam sitting.
        If template_id given, sections are copied from template (unless overridden).
        is_ad_hoc=True allows free-form sections without a template [FLEX].
        """
        if not exam_date:
            raise ValueError("exam_date (YYYY-MM-DD) is required")
        # basic date validation
        try:
            date.fromisoformat(exam_date)
        except ValueError:
            raise ValueError(f"Invalid exam_date: {exam_date}")

        resolved_sections = sections
        if template_id and not resolved_sections:
            tpl = self.get_template(template_id)
            if not tpl:
                raise ValueError(f"Template not found: {template_id}")
            resolved_sections = copy.deepcopy(tpl.get('sections') or [])
            if not subject:
                subject = tpl.get('subject', '')
        if not resolved_sections:
            if is_ad_hoc:
                resolved_sections = [{
                    'key': 'score',
                    'name': 'Score',
                    'section_type': 'custom',
                    'max_marks': 100,
                    'question_count': 0,
                    'duration_minutes': 0,
                    'weight': 1.0,
                    'immediate_result': False,
                }]
            else:
                # ensure default template exists and use it
                default = self.ensure_default_template(actor_id)
                template_id = default['id']
                resolved_sections = copy.deepcopy(default.get('sections') or [])

        exam = Exam(
            tenant_id=str(self.tenant_context.tenant_id),
            template_id=template_id,
            batch_id=batch_id,
            name=name,
            exam_date=exam_date,
            chapter_or_topic=chapter_or_topic,
            subject=subject,
            status=status,
            sections=resolved_sections,
            is_ad_hoc=is_ad_hoc,
            notes=notes,
        )
        rid = self.data_layer.create('exams', exam.to_dict())
        stored = self.data_layer.get('exams', rid)
        self.audit_service.log_create(
            table_name='exams',
            record_id=rid,
            new_state=stored or exam.to_dict(),
            actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
        )
        self._persist_audit()
        self._queue_sync('create', 'exams', str(rid), None, stored)
        return str(rid)

    def get_exam(self, exam_id: str) -> Optional[Dict[str, Any]]:
        return self.data_layer.get('exams', uuid.UUID(exam_id))

    def list_exams(
        self,
        batch_id: Optional[str] = None,
        chapter_or_topic: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        rows = self.data_layer.get_all('exams')
        if batch_id:
            rows = [r for r in rows if r.get('batch_id') == batch_id]
        if chapter_or_topic:
            rows = [r for r in rows if r.get('chapter_or_topic') == chapter_or_topic]
        if status:
            rows = [r for r in rows if r.get('status') == status]
        if from_date:
            rows = [r for r in rows if (r.get('exam_date') or '') >= from_date]
        if to_date:
            rows = [r for r in rows if (r.get('exam_date') or '') <= to_date]
        rows.sort(key=lambda r: r.get('exam_date', ''), reverse=True)
        return rows

    def update_exam(
        self,
        exam_id: str,
        actor_id: Optional[str] = None,
        **kwargs,
    ) -> bool:
        old = self.get_exam(exam_id)
        if not old:
            return False
        allowed = {
            'name', 'exam_date', 'batch_id', 'chapter_or_topic', 'subject',
            'status', 'sections', 'notes', 'is_ad_hoc',
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if 'exam_date' in updates:
            try:
                date.fromisoformat(updates['exam_date'])
            except ValueError:
                raise ValueError(f"Invalid exam_date: {updates['exam_date']}")
        if 'status' in updates and updates['status'] not in (
            EXAM_DRAFT, EXAM_SCHEDULED, 'in_progress', EXAM_COMPLETED, EXAM_CANCELLED,
        ):
            raise ValueError(f"Invalid status: {updates['status']}")
        updates['updated_at'] = _utcnow()
        ok = self.data_layer.update('exams', uuid.UUID(exam_id), updates)
        if ok:
            new = self.get_exam(exam_id)
            self.audit_service.log_update(
                table_name='exams',
                record_id=uuid.UUID(exam_id),
                old_state=old,
                new_state=new or updates,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._persist_audit()
            self._queue_sync('update', 'exams', exam_id, old, new)
        return ok

    def complete_exam(self, exam_id: str, actor_id: Optional[str] = None) -> bool:
        return self.update_exam(exam_id, actor_id=actor_id, status=EXAM_COMPLETED)

    # ── Results entry (manual only) [BULLET] ──────────────────────────

    def enter_result(
        self,
        exam_id: str,
        student_id: str,
        section_scores: Optional[List[Dict[str, Any]]] = None,
        is_absent: bool = False,
        notes: str = '',
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Manual entry of a student's result for an exam.
        section_scores: [{key, marks_obtained, max_marks?, notes?}]
        If max_marks omitted, taken from exam.sections.
        Upserts on (exam_id, student_id) — permanent record, never deleted.
        """
        exam = self.get_exam(exam_id)
        if not exam:
            raise ValueError(f"Exam not found: {exam_id}")
        student = self.data_layer.get('students', uuid.UUID(student_id))
        if not student:
            raise ValueError(f"Student not found: {student_id}")

        # Build scores with max_marks from exam if missing
        exam_sections = {s.get('key'): s for s in (exam.get('sections') or [])}
        scores: List[Dict[str, Any]] = []
        if not is_absent:
            for raw in (section_scores or []):
                key = raw.get('key') or raw.get('section_key') or 'score'
                es = exam_sections.get(key, {})
                max_m = float(raw.get('max_marks', es.get('max_marks', 0)) or 0)
                obtained = float(raw.get('marks_obtained', 0) or 0)
                if obtained < 0:
                    raise ValueError(f"marks_obtained cannot be negative for section {key}")
                if max_m > 0 and obtained > max_m:
                    raise ValueError(
                        f"marks_obtained {obtained} exceeds max_marks {max_m} for section {key}"
                    )
                scores.append({
                    'key': key,
                    'name': raw.get('name', es.get('name', key)),
                    'section_type': raw.get('section_type', es.get('section_type', 'custom')),
                    'marks_obtained': obtained,
                    'max_marks': max_m,
                    'notes': raw.get('notes', ''),
                })

        existing = self.get_result(exam_id, student_id)
        result = ExamResult(
            id=existing['id'] if existing else None,
            tenant_id=str(self.tenant_context.tenant_id),
            exam_id=exam_id,
            student_id=student_id,
            batch_id=student.get('batch_id', exam.get('batch_id', '')),
            roll=student.get('roll', ''),
            exam_date=exam.get('exam_date', ''),
            chapter_or_topic=exam.get('chapter_or_topic', ''),
            section_scores=scores,
            is_absent=is_absent,
            entered_by=actor_id,
            notes=notes,
        )
        payload = result.to_dict()

        if existing:
            old = dict(existing)
            payload['updated_at'] = _utcnow()
            # keep original id / created_at
            payload['id'] = existing['id']
            payload['created_at'] = existing.get('created_at', payload['created_at'])
            self.data_layer.update('exam_results', uuid.UUID(existing['id']), payload)
            new = self.data_layer.get('exam_results', uuid.UUID(existing['id']))
            self.audit_service.log_update(
                table_name='exam_results',
                record_id=uuid.UUID(existing['id']),
                old_state=old,
                new_state=new or payload,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._persist_audit()
            self._queue_sync('update', 'exam_results', existing['id'], old, new)
            return new or payload
        else:
            rid = self.data_layer.create('exam_results', payload)
            stored = self.data_layer.get('exam_results', rid)
            self.audit_service.log_create(
                table_name='exam_results',
                record_id=rid,
                new_state=stored or payload,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
            self._persist_audit()
            self._queue_sync('create', 'exam_results', str(rid), None, stored)
            return stored or payload

    def enter_bulk_results(
        self,
        exam_id: str,
        entries: List[Dict[str, Any]],
        actor_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Bulk manual entry. Each entry: {student_id, section_scores?, is_absent?, notes?}
        Continues on per-student errors; returns list of successful results.
        """
        out = []
        for e in entries:
            sid = e.get('student_id')
            if not sid:
                continue
            try:
                r = self.enter_result(
                    exam_id=exam_id,
                    student_id=sid,
                    section_scores=e.get('section_scores'),
                    is_absent=bool(e.get('is_absent', False)),
                    notes=e.get('notes', ''),
                    actor_id=actor_id,
                )
                out.append(r)
            except (ValueError, Exception):
                continue
        return out

    def get_result(self, exam_id: str, student_id: str) -> Optional[Dict[str, Any]]:
        for r in self.data_layer.get_all('exam_results'):
            if r.get('exam_id') == exam_id and r.get('student_id') == student_id:
                return r
        return None

    def get_student_results(
        self,
        student_id: str,
        chapter_or_topic: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Permanent history for one student [BULLET]."""
        rows = [
            r for r in self.data_layer.get_all('exam_results')
            if r.get('student_id') == student_id
        ]
        if chapter_or_topic:
            rows = [r for r in rows if r.get('chapter_or_topic') == chapter_or_topic]
        if from_date:
            rows = [r for r in rows if (r.get('exam_date') or '') >= from_date]
        if to_date:
            rows = [r for r in rows if (r.get('exam_date') or '') <= to_date]
        rows.sort(key=lambda r: r.get('exam_date', ''), reverse=True)
        return rows

    def get_exam_results(self, exam_id: str) -> List[Dict[str, Any]]:
        rows = [
            r for r in self.data_layer.get_all('exam_results')
            if r.get('exam_id') == exam_id
        ]
        rows.sort(key=lambda r: (r.get('roll', ''), r.get('student_id', '')))
        return rows

    def mark_absent(
        self,
        exam_id: str,
        student_id: str,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.enter_result(
            exam_id=exam_id,
            student_id=student_id,
            section_scores=[],
            is_absent=True,
            actor_id=actor_id,
        )

    # ── Analytics [NEW] ───────────────────────────────────────────────

    def exam_summary(self, exam_id: str) -> Dict[str, Any]:
        """Cohort stats for one exam: mean, median, percentiles, section averages."""
        exam = self.get_exam(exam_id)
        if not exam:
            raise ValueError(f"Exam not found: {exam_id}")
        results = [r for r in self.get_exam_results(exam_id) if not r.get('is_absent')]
        percentages = [float(r.get('percentage', 0) or 0) for r in results]
        totals = [float(r.get('total_obtained', 0) or 0) for r in results]

        section_keys = [s.get('key') for s in (exam.get('sections') or [])]
        section_avgs: Dict[str, float] = {}
        for key in section_keys:
            vals = []
            for r in results:
                for sc in (r.get('section_scores') or []):
                    if sc.get('key') == key:
                        vals.append(float(sc.get('marks_obtained', 0) or 0))
            section_avgs[key] = round(statistics.mean(vals), 2) if vals else 0.0

        def pct(p: float) -> Optional[float]:
            if not percentages:
                return None
            s = sorted(percentages)
            k = (len(s) - 1) * (p / 100.0)
            f = int(k)
            c = min(f + 1, len(s) - 1)
            return round(s[f] + (s[c] - s[f]) * (k - f), 2)

        return {
            'exam_id': exam_id,
            'exam_name': exam.get('name'),
            'exam_date': exam.get('exam_date'),
            'chapter_or_topic': exam.get('chapter_or_topic'),
            'n_present': len(results),
            'n_absent': len([r for r in self.get_exam_results(exam_id) if r.get('is_absent')]),
            'mean_percentage': round(statistics.mean(percentages), 2) if percentages else None,
            'median_percentage': round(statistics.median(percentages), 2) if percentages else None,
            'p25': pct(25),
            'p75': pct(75),
            'max_percentage': max(percentages) if percentages else None,
            'min_percentage': min(percentages) if percentages else None,
            'mean_total': round(statistics.mean(totals), 2) if totals else None,
            'section_averages': section_avgs,
            'total_max': exam.get('total_max_marks') or sum(
                float(s.get('max_marks', 0) or 0) for s in (exam.get('sections') or [])
            ),
        }

    def topic_heatmap(
        self,
        batch_id: Optional[str] = None,
        student_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Per-topic average percentage (weakness heatmap data).
        Optionally scoped to a batch or single student.
        """
        rows = self.data_layer.get_all('exam_results')
        if batch_id:
            rows = [r for r in rows if r.get('batch_id') == batch_id]
        if student_id:
            rows = [r for r in rows if r.get('student_id') == student_id]
        rows = [r for r in rows if not r.get('is_absent') and r.get('chapter_or_topic')]

        by_topic: Dict[str, List[float]] = {}
        for r in rows:
            topic = r.get('chapter_or_topic') or 'unknown'
            by_topic.setdefault(topic, []).append(float(r.get('percentage', 0) or 0))

        out = []
        for topic, vals in sorted(by_topic.items()):
            out.append({
                'chapter_or_topic': topic,
                'n': len(vals),
                'mean_percentage': round(statistics.mean(vals), 2),
                'median_percentage': round(statistics.median(vals), 2),
                'min_percentage': min(vals),
                'max_percentage': max(vals),
            })
        return out

    def mcq_vs_written_gap(
        self,
        exam_id: Optional[str] = None,
        student_id: Optional[str] = None,
        batch_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        MCQ percentage vs written/CQ percentage gap per student (or aggregated).
        Positive gap = stronger on MCQ than written.
        """
        rows = self.data_layer.get_all('exam_results')
        if exam_id:
            rows = [r for r in rows if r.get('exam_id') == exam_id]
        if student_id:
            rows = [r for r in rows if r.get('student_id') == student_id]
        if batch_id:
            rows = [r for r in rows if r.get('batch_id') == batch_id]
        rows = [r for r in rows if not r.get('is_absent')]

        out = []
        for r in rows:
            mcq_obt = mcq_max = written_obt = written_max = 0.0
            for sc in (r.get('section_scores') or []):
                st = sc.get('section_type', '')
                obt = float(sc.get('marks_obtained', 0) or 0)
                mx = float(sc.get('max_marks', 0) or 0)
                if st == SECTION_MCQ:
                    mcq_obt += obt
                    mcq_max += mx
                elif st in (SECTION_WRITTEN, SECTION_CQ):
                    written_obt += obt
                    written_max += mx
            mcq_pct = (100.0 * mcq_obt / mcq_max) if mcq_max > 0 else None
            written_pct = (100.0 * written_obt / written_max) if written_max > 0 else None
            gap = None
            if mcq_pct is not None and written_pct is not None:
                gap = round(mcq_pct - written_pct, 2)
            out.append({
                'student_id': r.get('student_id'),
                'exam_id': r.get('exam_id'),
                'roll': r.get('roll'),
                'mcq_percentage': round(mcq_pct, 2) if mcq_pct is not None else None,
                'written_percentage': round(written_pct, 2) if written_pct is not None else None,
                'gap': gap,
            })
        return out

    def students_likely_to_struggle(
        self,
        batch_id: str,
        recent_exam_limit: int = 3,
        low_score_threshold: float = 40.0,
        low_attendance_days: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Heuristic: students with low recent exam averages and/or low attendance.
        Uses AttendanceService when injected for attendance signal.
        """
        students = [
            s for s in self.data_layer.get_all('students')
            if s.get('batch_id') == batch_id and s.get('is_active', True)
        ]
        # recent exams for batch
        exams = self.list_exams(batch_id=batch_id, status=EXAM_COMPLETED)
        exams = exams[:recent_exam_limit] if exams else []
        exam_ids = {e['id'] for e in exams}

        flagged = []
        for s in students:
            sid = s['id']
            results = [
                r for r in self.get_student_results(sid)
                if r.get('exam_id') in exam_ids and not r.get('is_absent')
            ]
            avg = None
            if results:
                avg = round(statistics.mean(
                    float(r.get('percentage', 0) or 0) for r in results
                ), 2)

            attendance_days = None
            if self.attendance_service:
                try:
                    # current month attended days
                    today = date.today()
                    attendance_days = self.attendance_service.count_attended_days(
                        sid, year=today.year, month=today.month
                    )
                except Exception:
                    attendance_days = None

            low_score = avg is not None and avg < low_score_threshold
            low_att = (
                low_attendance_days is not None
                and attendance_days is not None
                and attendance_days < low_attendance_days
            )
            if low_score or low_att:
                flagged.append({
                    'student_id': sid,
                    'name': s.get('name'),
                    'roll': s.get('roll'),
                    'recent_avg_percentage': avg,
                    'attended_days_this_month': attendance_days,
                    'reason': (
                        'low_score+low_attendance' if (low_score and low_att)
                        else ('low_score' if low_score else 'low_attendance')
                    ),
                })
        flagged.sort(key=lambda x: (x.get('recent_avg_percentage') or 0))
        return flagged

    def cohort_comparison(
        self,
        exam_id: str,
    ) -> Dict[str, Any]:
        """Student ranks vs batch mean for one exam."""
        summary = self.exam_summary(exam_id)
        results = [r for r in self.get_exam_results(exam_id) if not r.get('is_absent')]
        mean = summary.get('mean_percentage')
        ranked = sorted(
            results,
            key=lambda r: float(r.get('percentage', 0) or 0),
            reverse=True,
        )
        leaderboard = []
        for i, r in enumerate(ranked, start=1):
            pct = float(r.get('percentage', 0) or 0)
            leaderboard.append({
                'rank': i,
                'student_id': r.get('student_id'),
                'roll': r.get('roll'),
                'percentage': pct,
                'vs_mean': round(pct - mean, 2) if mean is not None else None,
            })
        return {
            'exam_id': exam_id,
            'batch_mean': mean,
            'n': len(ranked),
            'leaderboard': leaderboard,
        }

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
