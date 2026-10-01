#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--dev-json", default="")
    args = ap.parse_args()
    if not args.json or not Path(args.json).exists():
        print("no npm audit json"); return 0
    data = json.loads(Path(args.json).read_text())
    vulns = data.get("vulnerabilities") or {}
    high = []
    for name, meta in vulns.items():
        sev = (meta.get("severity") or "").lower()
        if sev in ("high", "critical"):
            high.append(f"{name}:{sev}")
    if args.dev_json and Path(args.dev_json).exists():
        dev = json.loads(Path(args.dev_json).read_text())
        for name, meta in (dev.get("vulnerabilities") or {}).items():
            sev = (meta.get("severity") or "").lower()
            if sev in ("high", "critical") and name not in {h.split(":")[0] for h in high}:
                print(f"DEV-ONLY warning: {name}:{sev}")
    if high:
        print("npm production high/critical:\n" + "\n".join(high[:40]))
        sys.exit(1)
    print("npm_audit_gate OK (production tree)")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
