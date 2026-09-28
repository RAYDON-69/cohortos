"""Agent safety helpers: cloud LLM toggle (default OFF), PII redaction, audit."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional


def cloud_llm_allowed(ai_keys_section: Optional[Dict[str, Any]] = None) -> bool:
    """Per-tenant toggle; default OFF (roadmap §4)."""
    sec = ai_keys_section or {}
    return bool(sec.get("cloud_llm_enabled") is True or sec.get("cloud_llm_enabled") == "1")


_PHONE = re.compile(r"(?:\+?880|0)?1[3-9]\d{8}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_NID = re.compile(r"\b\d{10,17}\b")


def redact_pii(text: str) -> str:
    t = text or ""
    t = _PHONE.sub("[PHONE]", t)
    t = _EMAIL.sub("[EMAIL]", t)
    t = _NID.sub("[ID]", t)
    return t


WRITE_TOOLS = frozenset(
    {"create_automation_rule", "set_automation_enabled", "admit_student", "mark_attendance"}
)

ALLOWED_WRITE_ROLES = frozenset({"owner", "desk", "admin", "teacher"})


def role_can_write(role: str) -> bool:
    return (role or "").lower() in ALLOWED_WRITE_ROLES
