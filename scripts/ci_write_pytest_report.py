#!/usr/bin/env python3
"""Parse pytest output + optional JSON report into a structured gate report."""
import json, re, sys
from pathlib import Path

def main():
    log = Path(sys.argv[1]).read_text(errors="ignore") if len(sys.argv) > 1 else ""
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/pytest-report.json")
    extra = {}
    for p in ("/tmp/auth-matrix-report.json",):
        if Path(p).exists():
            try:
                extra.update(json.loads(Path(p).read_text()))
            except Exception:
                pass
    failed = re.findall(r"FAILED\s+(\S+)\s+-?\s*(.*)", log)
    passed = len(re.findall(r"\bPASSED\b|\.", log))  # crude
    doc = {
        "tests_failed": [{"node": a, "detail": b[:300]} for a, b in failed],
        "failed_count": len(failed),
        "passed_hint": log.strip().splitlines()[-3:] if log.strip() else [],
        "log_tail": log[-6000:],
        **extra,
    }
    # exit code file
    rc_path = Path("/tmp/pytest-rc")
    rc = int(rc_path.read_text()) if rc_path.exists() else (1 if failed else 0)
    doc["exit_code"] = rc
    out.write_text(json.dumps(doc, indent=2))
    print(json.dumps({k: doc[k] for k in ("failed_count", "total_routes", "unclassified") if k in doc}))
    return rc

if __name__ == "__main__":
    raise SystemExit(main())
