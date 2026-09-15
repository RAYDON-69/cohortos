# Portion 2 Summary — Admission + Batch Config

## Status: production-ready (2026-08-17)

### Components
1. **Roll encoder** (`services/roll_encoder.py`)
   - LOCKED default: `[DaySet 3][Hour 2][Serial 3]`
   - SPEC example verified: Sat+Mon+Wed 14:00 #33 → `02114033`
   - Plain serial + custom pattern schemes

2. **Admission service** (`services/admission_service.py`)
   - Batch CRUD, extra sessions, templates (export strips AI prompts)
   - admit_student with auto-roll, join-code generation
   - detect_duplicates → DuplicateStudentError with concrete matches
   - migrate_student_roll_batch: atomic, full history, rollback, logged
   - generate_join_code / link_account (Module 8 primary + staff fallback)

3. **Models** (`models/admission.py`)
   - Batch, BatchTemplate, Student, JoinCode, DuplicateMatch, MigrationRecord

4. **Migration** `migrations/005_admission.sql`
   - batches, batch_templates, students, join_codes, migration_logs
   - history table stubs: attendance, payments, exam_results, threads

### Tests (44)
- Roll encoding + edge (serial exhaust, invalid day)
- Batch management + templates + extra sessions
- Admission + duplicate phone/parent/force idempotent
- Migration with seeded history + noop + audit log
- Join codes: single-use, regenerate invalidates, expiry, staff manual
- Offline path, tenant isolation, Bangla names, custom fields

### Full suite: 114 passed
