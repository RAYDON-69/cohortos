# Portion 8 — AI: CohortOS Solve + Teach (Module 9)

**Goal**: Production-ready domain services for student tutor (Solve) and teacher co-pilot (Teach), with grounding, self-verification, confidence scoring, teacher review gate, quotas, caching, and graceful offline/429 degradation.

**Confirmed decisions (user 2026-08-17)**:
1. Pluggable LLMProvider + MockLLMProvider + GeminiProvider stub; degrade on 429/offline.
2. AI threads keyed to student_id (admission id) only.
3. Retrieval = Content Vault topic/keyword overlap; zero chunks → ungrounded → review gate.
4. OCR = interface + stub ("needs teacher review / not implemented").
5. Continue p7 tree → CohortOS_portions_0-8_production.zip.

## Acceptance criteria

- [ ] LLMProvider ABC + Mock (deterministic) + Gemini stub (offline/429 degrade)
- [ ] RetrievalService over Content Vault; cites resource ids; empty → ungrounded
- [ ] Solve pipeline: classify → retrieve → generate (Answer/How/Why) → self-verify → confidence → cache/quota
- [ ] Teach pipeline: grounded generation only; review queue; version history; style profile; analytics ranking stub
- [ ] No Teach item reaches students without explicit teacher approve
- [ ] Per-student daily caps (MCQ vs written); cache semantic-ish match; rate-limit queue
- [ ] AIThread / AIMessage by student_id; teacher can annotate
- [ ] OCRAssist stub only
- [ ] Wired into CohortOSApp
- [ ] Migration 010_ai.sql
- [ ] tests/test_ai.py covering grounding, verify mismatch, review gate, quota, offline, 429
- [ ] Full tree still green + new tests green
- [ ] Zip 0–8

## Files

- models/ai.py
- services/llm_provider.py
- services/retrieval_service.py
- services/ai_quota_service.py
- services/ai_solve_service.py
- services/ai_teach_service.py
- services/app.py (wire)
- migrations/010_ai.sql
- tests/test_ai.py
- PORTION_8_SUMMARY.md, BUILD_PLAN update
