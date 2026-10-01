#!/usr/bin/env python3
import json, sys
from pathlib import Path
a, b, out = sys.argv[1], sys.argv[2], sys.argv[3]
doc = {}
for p, k in ((a, "bandit"), (b, "semgrep")):
    path = Path(p)
    if path.exists():
        try:
            doc[k] = json.loads(path.read_text())
        except Exception as e:
            doc[k] = {"error": str(e)}
Path(out).write_text(json.dumps(doc, indent=2))
