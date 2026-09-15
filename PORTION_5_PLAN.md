# Portion 5 — Exams / Results (SPEC Module 4)

## Status
In progress → production-ready target

## Acceptance criteria
1. **Exam templates [FLEX]**  
   - Default “main exam” template: 15 MCQ (9 min), 6 physics-maths (60 marks, 18 min), 1 CQ (10 marks).  
   - Separate optional “open book” type (low priority).  
   - Centres can create/edit/delete custom templates (sections with name, type, max_marks, duration_minutes, weight).  
   - Templates are per-tenant; can be scoped to batch/subject later.

2. **Manual entry only [BULLET]**  
   - All scores entered by typing. No voice/OCR paths.

3. **Extra / ad-hoc exams [FLEX]**  
   - Create exam instances outside any template (custom name, date, free-form score fields).

4. **Permanent history [BULLET]**  
   - Every result lives forever.  
   - On roll/batch migration (Portion 2) results move with the student (`exam_results` already in HISTORY_TABLES).  
   - Never delete results on student soft-delete.

5. **Batch-level analytics [NEW]** (read-only views)  
   - Per-topic / per-section average & weakness heatmap data.  
   - MCQ vs written gap per student and cohort.  
   - Cohort comparison (batch mean, percentiles).  
   - Simple “likely to struggle next” signal from low recent scores + low attendance days (uses AttendanceService when injected).

6. **Cross-cutting**  
   - Offline-first core writes.  
   - Tenant-scoped.  
   - Every mutation audit-logged.  
   - Sync-queue ready.  
   - Timezone-aware timestamps.

## Files
- `models/exam.py` (new)
- `services/exam_service.py` (new)
- `migrations/008_exams.sql` (new)
- `tests/test_exam.py` (new)
- `PORTION_5_PLAN.md`, `PORTION_5_SUMMARY.md`
- Touch only: admission HISTORY_TABLES already contains `exam_results` — no change needed there unless schema rename.

## Verify
```bash
python -m pytest tests/test_exam.py -v
python -m pytest tests/ -q
```
