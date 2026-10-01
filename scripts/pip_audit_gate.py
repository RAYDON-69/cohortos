#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path
from datetime import date

def load_allow(path):
    out = {}
    p = Path(path)
    if not p.exists():
        return out
    for ln in p.read_text().splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        parts = [x.strip() for x in ln.split("|")]
        if len(parts) >= 3:
            out[parts[0]] = {"reason": parts[1], "expires": parts[2]}
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--allowlist", default="docs/PIP_AUDIT_ALLOWLIST.txt")
    args = ap.parse_args()
    allow = load_allow(args.allowlist)
    data = json.loads(Path(args.json).read_text()) if args.json and Path(args.json).exists() else []
    # pip-audit json formats vary
    deps = data if isinstance(data, list) else data.get("dependencies") or data.get("vulns") or []
    bad = []
    today = date.today().isoformat()
    for dep in deps:
        name = dep.get("name") or dep.get("Name") or ""
        version = dep.get("version") or dep.get("Version") or ""
        vulns = dep.get("vulns") or dep.get("vulnerabilities") or []
        if not vulns and dep.get("id"):
            vulns = [dep]
        for v in vulns:
            vid = v.get("id") or v.get("ID") or ""
            fixes = v.get("fix_versions") or v.get("Fix Versions") or []
            if vid in allow:
                exp = allow[vid]["expires"]
                if exp >= today:
                    print(f"ALLOWED {vid} until {exp}: {allow[vid]['reason']}")
                    continue
            if fixes:
                bad.append(f"{name} {version} {vid} fix={fixes}")
            else:
                # no fix and not allowlisted
                if vid not in allow:
                    bad.append(f"{name} {version} {vid} no_fix")
    if bad:
        print("UNFIXED HIGH/CRITICAL:\n" + "\n".join(bad[:40]))
        sys.exit(1)
    print("pip_audit_gate OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
