# CohortOS Domain Package — Install & Run (Portion 7)

## Requirements

- Python 3.10+
- `pytest` (for tests only)

No external runtime services required for core Modules 1–5. Everything works offline with the in-memory `DataAccessLayer` (default). SQLite migrations are available for the sync/notification queues.

## Install (editable)

```bash
cd cohortos_p7   # or the extracted package root
pip install -e ".[dev]"
# or simply:
pip install -r requirements.txt
export PYTHONPATH=.
```

## Verify

```bash
python -m pytest tests/ -q
# Expected: 239 passed (or higher)
```

## Bootstrap a centre (Python)

```python
from services.app import create_app

app = create_app(mode="offline-first")
summary = app.bootstrap_centre(
    name="Swapan Physics Coaching",
    code="BARISHAL-PHY",
    create_sample_batches=True,
)
print(summary)
# Use app.admission / app.attendance / app.payment / app.exam / app.content
```

## SQLite migrations (optional, for durable sync/notification tables)

```bash
python scripts/migrate.py --db /path/to/cohortos.db
# Idempotent. Applies 003–009 (SQLite-oriented). 001–002 are Postgres reference only.
```

## Health check

```python
from services.app import create_app
print(create_app().health())
```

## Integration points

- **Electron desktop**: spawn or embed a Python process, call `create_app` / methods via stdin/JSON-RPC or pywebview bridge.
- **FastAPI**: `Depends(create_app)` or a singleton per tenant; expose REST that delegates to `app.admission`, etc.
- **Tests**: always use `create_app()` so all modules share one `DataAccessLayer`.

See `HANDOFF.md` for what is deliberately out of scope and how the package maps to SPEC Modules 1–5 + §7.

## Production API environment (required)

Before starting the HTTP API in production, export:

```bash
export COHORTOS_JWT_SECRET="a-long-random-secret"
export COHORTOS_AUTH_DB="/var/lib/cohortos/auth.db"
export COHORTOS_CLOUD_DB="/var/lib/cohortos/cloud_sync.db"
```

Then:

```python
from api.main import create_api_app_or_raise
app = create_api_app_or_raise()  # raises AuthConfigError if any var is missing or :memory:
```

If these are skipped, session families and the sync log live only in RAM and disappear on restart — logged-in users are forced to re-authenticate, and cloud sync cannot recover a destroyed device.
