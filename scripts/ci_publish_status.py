#!/usr/bin/env python3
"""Write status-<gate>-<sha>.json to ci-reports."""
from __future__ import annotations
import json, os, re, sys, subprocess
from pathlib import Path

_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_GATE_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")

def main() -> int:
    gate = sys.argv[1]
    conclusion = sys.argv[2]
    failed = sys.argv[3:] if len(sys.argv) > 3 else []
    if not _GATE_RE.match(gate):
        print("invalid gate name", gate)
        return 2
    if conclusion not in ("success", "failure", "cancelled", "skipped"):
        print("invalid conclusion", conclusion)
        return 2
    sha = os.environ.get("GITHUB_SHA") or "unknown"
    if sha != "unknown" and not _SHA_RE.match(sha):
        print("invalid GITHUB_SHA")
        return 2
    doc = {
        "gate": gate,
        "sha": sha,
        "conclusion": conclusion,
        "failed": failed,
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
    }
    local = Path(f"/tmp/status-{gate}.json")
    local.write_text(json.dumps(doc, indent=2))
    remote = f"status-{gate}-{sha}.json"
    # list-form args only; remote name validated
    if not re.match(r"^[a-zA-Z0-9_.-]+\.json$", remote):
        print("invalid remote name")
        return 2
    pub = Path(__file__).parent / "publish_ci_report.py"
    subprocess.call([sys.executable, str(pub), str(local), remote])  # nosemgrep: dangerous-subprocess-use-tainted-env-args — SHA/gate validated above
    print(json.dumps(doc))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
