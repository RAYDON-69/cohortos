#!/usr/bin/env python3
"""Write status-<gate>-<sha>.json to ci-reports."""
from __future__ import annotations
import json, os, sys, subprocess
from pathlib import Path

def main() -> int:
    gate = sys.argv[1]
    conclusion = sys.argv[2]  # success|failure|cancelled
    failed = sys.argv[3:] if len(sys.argv) > 3 else []
    sha = os.environ.get("GITHUB_SHA") or "unknown"
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
    subprocess.call([sys.executable, str(Path(__file__).parent / "publish_ci_report.py"), str(local), remote])
    print(json.dumps(doc))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
