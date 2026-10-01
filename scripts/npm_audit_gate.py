#!/usr/bin/env python3
"""Fail on high/critical npm audit unless only in optional peer trees we cannot fix without majors."""
import argparse, json, sys
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    args = ap.parse_args()
    if not args.json or not Path(args.json).exists():
        print("no npm audit json")
        return 0
    data = json.loads(Path(args.json).read_text())
    vulns = data.get("vulnerabilities") or {}
    high = []
    for name, meta in vulns.items():
        sev = (meta.get("severity") or "").lower()
        if sev in ("high", "critical"):
            via = meta.get("via") or []
            high.append(f"{name}:{sev}")
    if high:
        print("npm high/critical:\n" + "\n".join(high[:40]))
        # Still exit 1 — force upgrades via package updates separately
        sys.exit(1)
    print("npm_audit_gate OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
