#!/usr/bin/env python3
import json, sys
from pathlib import Path
src = Path(sys.argv[1]) if len(sys.argv)>1 else Path("/tmp/semgrep.json")
out = Path(sys.argv[2]) if len(sys.argv)>2 else Path("/tmp/semgrep-report.json")
data = json.loads(src.read_text()) if src.exists() else {}
findings = []
for r in data.get("results") or []:
    findings.append({
        "rule": r.get("check_id"),
        "path": r.get("path"),
        "line": (r.get("start") or {}).get("line"),
        "severity": (r.get("extra") or {}).get("severity"),
        "message": ((r.get("extra") or {}).get("message") or "")[:160],
    })
doc = {"findings": findings, "count": len(findings)}
out.write_text(json.dumps(doc, indent=2))
print("semgrep_count", len(findings))
