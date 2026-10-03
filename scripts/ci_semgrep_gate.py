#!/usr/bin/env python3
"""Fail on ERROR-severity semgrep findings; print all findings."""
from __future__ import annotations
import json, sys
from pathlib import Path

def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/semgrep.json")
    if not path.exists():
        print("semgrep json missing")
        return 1
    data = json.loads(path.read_text())
    results = data.get("results") or []
    print(f"semgrep_total {len(results)}")
    errs = []
    for r in results:
        sev = (r.get("extra") or {}).get("severity") or r.get("severity")
        msg = (r.get("extra") or {}).get("message") or r.get("message") or ""
        line = f"{r.get('path')}:{r.get('start',{}).get('line')} [{sev}] {r.get('check_id')}: {msg[:120]}"
        print(line)
        if str(sev).upper() == "ERROR":
            errs.append(line)
    summary = Path("/tmp/semgrep_summary.txt")
    summary.write_text("\n".join(errs))
    print(f"semgrep_errors {len(errs)}")
    return 1 if errs else 0

if __name__ == "__main__":
    raise SystemExit(main())
