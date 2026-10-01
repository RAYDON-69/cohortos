#!/usr/bin/env python3
import json, re, sys
from pathlib import Path
log = Path(sys.argv[1]).read_text(errors="ignore") if len(sys.argv)>1 else ""
out = Path(sys.argv[2]) if len(sys.argv)>2 else Path("/tmp/fuzz-report.json")
fails = re.findall(r"(FAILED|Error|500|Server Error)[^\n]{0,200}", log)
doc = {
    "log_tail": log[-5000:],
    "fail_snippets": fails[:40],
    "fail_count": len(fails),
}
out.write_text(json.dumps(doc, indent=2))
print("fuzz_fail_snippets", len(fails))
# exit 1 if 500 mentioned as actual failure - leave to schemathesis exit code
