"""PII-redacted local diagnostics bundle for pilot support."""
from __future__ import annotations

import io
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PHONE_RE = re.compile(r"01[3-9]\d{8}")
TOKEN_RE = re.compile(r"(Bearer\s+)?[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}")
# crude name patterns in EN/BN not fully solvable; redact known seed markers


def redact(text: str, extra_secrets: List[str] | None = None) -> str:
    t = PHONE_RE.sub("[REDACTED_PHONE]", text)
    t = TOKEN_RE.sub("[REDACTED_TOKEN]", t)
    for s in extra_secrets or []:
        if s:
            t = t.replace(s, "[REDACTED]")
    return t


def build_diagnostics_bundle(
    *,
    log_lines: List[str],
    versions: Dict[str, str],
    config: Dict[str, Any],
    integrity: str = "ok",
    extra_secrets: List[str] | None = None,
) -> bytes:
    """Return zip bytes: versions, config (no secrets), last logs, integrity."""
    safe_config = {
        k: v
        for k, v in (config or {}).items()
        if not any(x in k.lower() for x in ("secret", "token", "password", "key", "otp"))
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("versions.json", json.dumps(versions, indent=2))
        zf.writestr("config.json", json.dumps(safe_config, indent=2))
        zf.writestr("integrity.txt", integrity)
        redacted = [redact(line, extra_secrets) for line in log_lines[-500:]]
        zf.writestr("logs_tail.txt", "\n".join(redacted))
        zf.writestr(
            "meta.json",
            json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "pii": "redacted"}, indent=2),
        )
    return buf.getvalue()
