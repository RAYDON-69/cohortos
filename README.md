# CohortOS Domain (Portions 0–7)

Offline-first domain services for a multi-staff coaching centre OS (admission, attendance, payments, exams, content vault, sync, notifications).

**Status**: Production-ready single-centre package. 239/239 tests green.

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

```python
from services.app import create_app
app = create_app()
app.bootstrap_centre(name="My Centre")
```

See `INSTALL.md` and `HANDOFF.md`. Source of truth: `SPEC.md`.
