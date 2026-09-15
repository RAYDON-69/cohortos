# Portion 8 — AI Solve + Teach (Module 9) — DONE

**Completed**: 2026-08-17  
**Status**: Production-ready

## Deliverables

| File | Role |
|------|------|
| `models/ai.py` | Threads, messages, generated items, style profiles, cache, quota |
| `services/llm_provider.py` | LLMProvider ABC, MockLLMProvider, GeminiProvider stub, parsers |
| `services/retrieval_service.py` | Vault keyword/topic retrieval + citations |
| `services/ai_quota_service.py` | Daily MCQ/written caps + query cache |
| `services/ai_solve_service.py` | Full Solve pipeline (classify→retrieve→generate→verify→gate) |
| `services/ai_teach_service.py` | Teach generation, review queue, style profile, analytics, OCR stub |
| `services/app.py` | Wired: `app.solve`, `app.teach`, `app.ai_quota`, `app.retrieval` |
| `migrations/010_ai.sql` | SQLite schema for AI tables |
| `tests/test_ai.py` | 21 tests |

## SPEC coverage (Module 9)

| Rule | Status |
|------|--------|
| Solve pipeline: classify, retrieve, Answer/How/Why, self-verify | ✅ |
| Grounded retrieval over Vault; zero chunks → ungrounded → review | ✅ |
| Confidence threshold → needs teacher review | ✅ |
| Threads keyed to student_id (admission) | ✅ |
| Teacher annotation on messages | ✅ |
| Teach: never invent unapproved content; ungrounded flagged | ✅ |
| Teacher review gate — no student visibility without approve | ✅ |
| Version history accept/edit/reject retained | ✅ |
| Few-shot style profile versioned | ✅ |
| Analytics ranked by impact (cohort × severity) | ✅ |
| Exam bank push only when approved | ✅ |
| Gemini free-tier default via stub; 429/offline degrade | ✅ |
| Per-student daily caps (MCQ vs written) | ✅ |
| Query cache | ✅ |
| OCR assist stub only | ✅ |

## Tests

- Portion 8: **21/21**
- Full tree: **260/260**

## Integration

```python
from services.app import create_app
from services.llm_provider import MockLLMProvider, GeminiProvider

app = create_app(llm=MockLLMProvider())  # or GeminiProvider(api_key=..., online=True)
result = app.solve.ask(student_id=sid, question="...", subject="physics", topic="mechanics")
item = app.teach.generate_item(item_type="mcq", subject="physics", topic="...", prompt="...", actor_id=owner)
app.teach.approve_item(item["id"], actor_id=owner)
```
