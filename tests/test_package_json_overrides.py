"""Guard: frontend/package.json overrides must be valid npm syntax."""
from __future__ import annotations
import json
import re
from pathlib import Path
import pytest

PKG_RE = re.compile(r"^(@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$")

def validate_overrides(overrides: dict) -> list[str]:
    errs = []
    if not isinstance(overrides, dict):
        return ["overrides must be object"]
    for key, val in overrides.items():
        if "*" in key or (key.count("/") > 1) or key.startswith("**/") or "/**" in key:
            errs.append(f"invalid override key (glob/yarn syntax): {key!r}")
        elif not PKG_RE.match(key):
            errs.append(f"invalid package name in overrides: {key!r}")
        if isinstance(val, dict):
            for k2, v2 in val.items():
                if "*" in k2 or not PKG_RE.match(k2):
                    errs.append(f"invalid nested override {key}.{k2!r}")
                if key.split("/")[-1] == k2 and isinstance(overrides.get(k2), str) and overrides.get(k2) != v2:
                    # same package different values root vs nested — warn as error
                    if overrides.get(k2) != v2:
                        errs.append(f"conflicting override values for {k2}: root={overrides.get(k2)!r} nested={v2!r}")
    return errs

def test_frontend_overrides_valid():
    data = json.loads(Path("frontend/package.json").read_text())
    errs = validate_overrides(data.get("overrides") or {})
    assert not errs, errs

def test_negative_control_star_star_braces_rejected():
    errs = validate_overrides({"**/braces": "3.0.3", "braces": ">=3.0.3"})
    assert any("**/braces" in e or "glob" in e for e in errs)
