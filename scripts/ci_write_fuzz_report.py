#!/usr/bin/env python3
import json, re, sys
from pathlib import Path
log = Path(sys.argv[1]).read_text(errors="ignore") if len(sys.argv) > 1 else ""
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/fuzz-report.json")
ops = re.findall(r"(GET|POST|PUT|PATCH|DELETE)\s+(/\S*)", log)
fails = []
for m in re.finditer(r"(FAILED|Error|500|Server Error)[^\n]{0,240}", log):
    fails.append(m.group(0)[:240])
has_5xx = bool(re.search(r"\b5\d\d\b", log)) and "not_a_server_error" in log
# also detect CLI misuse
cli_error = "No such option" in log
doc = {
    "operations_seen": list({f"{a} {b}" for a, b in ops})[:200],
    "operations_count": len(set(f"{a} {b}" for a, b in ops)),
    "fail_snippets": fails[:50],
    "fail_count": len(fails),
    "has_5xx": has_5xx,
    "cli_error": cli_error,
    "log_tail": log[-6000:],
    "log_head": log[:2000],
}
out.write_text(json.dumps(doc, indent=2))
print("fuzz_ops", doc["operations_count"], "fails", doc["fail_count"], "cli_error", cli_error)
if cli_error:
    raise SystemExit(1)
