#!/usr/bin/env python3
from __future__ import annotations
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "skip_budget.json"

def runtime_skips() -> int:
    for path in (Path("/tmp/junit-skip.xml"), Path("/tmp/junit-unit.xml"), Path("/tmp/junit-merge.xml"), Path("/tmp/unit-full-junit.xml")):
        if path.exists():
            m = re.search(r'skipped="(\d+)"', path.read_text(errors="replace"))
            if m:
                return int(m.group(1))
    return -1

def main() -> int:
    if not BASELINE.exists():
        print("missing tests/skip_budget.json"); return 2
    budget = json.loads(BASELINE.read_text())
    expected = int(budget.get("max_skips", budget.get("expected_skips", -1)))
    n = runtime_skips()
    print(json.dumps({"runtime_skips": n, "baseline": expected}, indent=2))
    if n < 0:
        print(f"FAIL could not measure runtime skips (baseline={expected})"); return 1
    if n != expected:
        print(f"FAIL skip count measured={n} baseline={expected}"); return 1
    print("skip budget exact match"); return 0

if __name__ == "__main__":
    raise SystemExit(main())
