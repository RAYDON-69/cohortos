#!/usr/bin/env python3
import json, sys
from pathlib import Path

def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/bandit.json")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/bandit-report.json")
    data = json.loads(src.read_text()) if src.exists() else {}
    findings = []
    for r in data.get("results") or []:
        sev = (r.get("issue_severity") or "").upper()
        if sev in ("MEDIUM", "HIGH"):
            findings.append({
                "file": r.get("filename"),
                "line": r.get("line_number"),
                "test_id": r.get("test_id"),
                "severity": sev,
                "text": (r.get("issue_text") or "")[:200],
            })
    doc = {
        "medium_plus": findings,
        "medium_plus_count": len(findings),
        "metrics": data.get("metrics"),
    }
    out.write_text(json.dumps(doc, indent=2))
    print(f"medium_plus_count={len(findings)}")
    return 1 if findings else 0

if __name__ == "__main__":
    raise SystemExit(main())
