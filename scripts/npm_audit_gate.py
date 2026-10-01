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
    high, mod = [], []
    for name, meta in vulns.items():
        sev = (meta.get("severity") or "").lower()
        via = str(meta.get("via"))[:120]
        fixed = ""
        fa = meta.get("fixAvailable")
        if isinstance(fa, dict):
            fixed = fa.get("version") or ""
        elif fa is True:
            fixed = "available"
        line = f"{name}:{sev}:via={via}:fixed_in={fixed}"
        if sev in ("high", "critical"):
            high.append(line)
        elif sev == "moderate":
            mod.append(line)
    for m in mod[:30]:
        print("MODERATE warning:", m)
    if high:
        print("npm production high/critical:\n" + "\n".join(high[:40]))
        sys.exit(1)
    print("npm_audit_gate OK (production tree; moderates as warnings only)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
