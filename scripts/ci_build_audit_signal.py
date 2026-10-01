#!/usr/bin/env python3
import json
from pathlib import Path

doc = {"job": "licenses-and-audit"}
for p, key in [
    ("/tmp/npm-audit-prod.json", "npm_prod"),
    ("/tmp/npm-audit-all.json", "npm_all"),
    ("/tmp/pip-audit.json", "pip_audit"),
    ("/tmp/pip-licenses.json", "pip_licenses"),
]:
    path = Path(p)
    if path.exists():
        try:
            doc[key] = json.loads(path.read_text())
        except Exception as e:
            doc[key] = {"error": str(e), "raw": path.read_text()[:2000]}
Path("/tmp/audit-signal.json").write_text(json.dumps(doc, indent=2)[:800000])
print("audit-signal keys", list(doc.keys()))
