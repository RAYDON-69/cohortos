#!/usr/bin/env python3
"""Fail if pytest skipped count exceeds committed baseline."""
from __future__ import annotations
import json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "skip_budget.json"


def static_skip_count() -> int:
    n = 0
    for p in (ROOT / "tests").rglob("*.py"):
        text = p.read_text(errors="replace")
        n += len(re.findall(r"pytest\.skip\(|@pytest\.mark\.skip(?:if)?\b", text))
    return n


def from_junit() -> int | None:
    for path in (Path("/tmp/junit-unit.xml"), Path("/tmp/unit-full-junit.xml")):
        if path.exists():
            text = path.read_text(errors="replace")
            m = re.search(r'skipped="(\d+)"', text)
            if m:
                return int(m.group(1))
    # tee log
    log = Path("/tmp/unit-full.out")
    if log.exists():
        m = re.search(r"(\d+)\s+skipped", log.read_text(errors="replace"))
        if m:
            return int(m.group(1))
    return None


def main() -> int:
    if not BASELINE.exists():
        print("missing tests/skip_budget.json")
        return 2
    budget = json.loads(BASELINE.read_text())
    max_skips = int(budget.get("max_skips", 0))
    static_n = static_skip_count()
    n = from_junit()
    if n is None:
        n = static_n
        print("using static skip marker count (no junit)")
    print(json.dumps({"skips": n, "max_skips": max_skips, "static_markers": static_n}, indent=2))
    if n > max_skips:
        print(f"FAIL skip budget {n} > {max_skips}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
