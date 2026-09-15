# Portion 5 — Exams / Results — DONE

**Completed**: 2026-08-17  
**Status**: Production-ready

## Files
- `models/exam.py` — ExamTemplate, Exam, ExamResult + default main-exam sections
- `services/exam_service.py` — templates, instances, manual entry, bulk, analytics
- `migrations/008_exams.sql` — exam_templates, exams, exam_results
- `tests/test_exam.py` — 29 tests
- `PORTION_5_PLAN.md`, `PORTION_5_SUMMARY.md`

## SPEC coverage (Module 4)

| Rule | Status |
|------|--------|
| [FLEX] Default main-exam structure (15 MCQ / 9 min, 6 maths 60 mk / 18 min, 1 CQ 10 mk) | ✅ |
| [FLEX] Custom templates per centre (any sections) | ✅ |
| Optional open-book type (low priority) | ✅ |
| [BULLET] Manual typing only | ✅ |
| [FLEX] Ad-hoc / extra exams | ✅ |
| [BULLET] Permanent history; never lost on roll/batch change | ✅ (HISTORY_TABLES + migration test) |
| [NEW] Per-topic weakness heatmap | ✅ `topic_heatmap` |
| [NEW] MCQ-vs-written gap | ✅ `mcq_vs_written_gap` |
| [NEW] Cohort comparison / ranks | ✅ `cohort_comparison` |
| [NEW] Students likely to struggle (score + optional attendance) | ✅ |
| Offline-first, tenant-scoped, audit-logged, sync-ready | ✅ |

## Tests
- Portion 5: **29/29**
- Full tree: **201/201**

## Integration notes
- Inject `AttendanceService` for attendance-aware “likely to struggle”.
- `exam_results` already listed in AdmissionService `HISTORY_TABLES` — roll/batch migration rewrites roll/batch_id.
- Analytics are pure read-only views over stored results.
