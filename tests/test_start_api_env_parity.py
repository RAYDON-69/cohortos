"""start-api composite must set every env key require_* demands."""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _required_env_from_auth():
    text = (ROOT / "api" / "auth.py").read_text()
    # require_durable_db_path("COHORTOS_AUTH_DB") etc and JWT
    keys = set(re.findall(r'require_durable_db_path\("([A-Z0-9_]+)"\)', text))
    keys |= set(re.findall(r'os\.environ\.get\("(COHORTOS_[A-Z0-9_]+)"\)', text))
    # hard requirements
    return {"COHORTOS_AUTH_DB", "COHORTOS_CLOUD_DB", "COHORTOS_JWT_SECRET"} | {
        k for k in keys if k in ("COHORTOS_AUTH_DB", "COHORTOS_CLOUD_DB", "COHORTOS_JWT_SECRET")
    }

def test_start_api_sets_required_keys():
    action = (ROOT / ".github" / "actions" / "start-api" / "action.yml").read_text()
    required = _required_env_from_auth()
    missing = []
    for k in required:
        # either in env: block or inputs mapped
        if k not in action and k.replace("COHORTOS_", "").lower() not in action.lower():
            # check common patterns
            if k == "COHORTOS_AUTH_DB" and "auth_db" not in action:
                missing.append(k)
            elif k == "COHORTOS_CLOUD_DB" and "cloud_db" not in action:
                missing.append(k)
            elif k == "COHORTOS_JWT_SECRET" and "jwt_secret" not in action:
                missing.append(k)
    assert not missing, f"start-api missing required env mapping: {missing}"
    assert "COHORTOS_AUTH_DB" in action
    assert "COHORTOS_CLOUD_DB" in action
    assert "COHORTOS_JWT_SECRET" in action
