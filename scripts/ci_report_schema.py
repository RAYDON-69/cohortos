#!/usr/bin/env python3
"""cohortos.ci-report/v1 helpers — scorecard keys off kind, not filename."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "cohortos.ci-report/v1"
VALID_KINDS = frozenset({
    "load", "bundle", "heap", "health", "installer", "fuzz", "bandit", "semgrep",
    "authmatrix", "ratelimit", "licenses", "e2e", "mutmut", "npm", "secrets",
})

def wrap(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown kind: {kind}")
    return {"schema": SCHEMA, "kind": kind, **payload}

def write_report(path: str | Path, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    doc = wrap(kind, payload)
    Path(path).write_text(json.dumps(doc, indent=2))
    return doc

def index_by_kind(reports: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Last write wins; duplicates collected under _duplicates."""
    by: Dict[str, Dict[str, Any]] = {}
    dups: List[str] = []
    for r in reports:
        if not isinstance(r, dict) or r.get("schema") != SCHEMA:
            continue
        k = r.get("kind")
        if not k:
            continue
        if k in by:
            dups.append(k)
        by[k] = r
    if dups:
        by["_duplicates"] = {"kinds": sorted(set(dups))}  # type: ignore
    return by
