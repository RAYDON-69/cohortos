#!/usr/bin/env python3
"""Build + publish a diag JSON to ci-reports. Always writes local file first."""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path

def main() -> int:
    if len(sys.argv) < 3:
        print("usage: publish_diag.py <name> <remote-basename.json> [extra.json]")
        return 2
    name, remote = sys.argv[1], sys.argv[2]
    extra = {}
    if len(sys.argv) > 3 and Path(sys.argv[3]).exists():
        try:
            extra = json.loads(Path(sys.argv[3]).read_text())
        except Exception as e:
            extra = {"extra_error": str(e)}
    api_log = Path("/tmp/api.log")
    doc = {
        "schema": "cohortos.ci-report/v1",
        "kind": "diag",
        "name": name,
        "api_log_tail": "\n".join(api_log.read_text(errors="replace").splitlines()[-200:]) if api_log.exists() else "",
        **extra,
    }
    local = Path(f"/tmp/diag-{name}.json")
    local.write_text(json.dumps(doc, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"\n## Diag {name}\n```\n")
            f.write(json.dumps({k: doc[k] for k in doc if k != "api_log_tail"}, indent=2)[:8000])
            f.write("\n```\n")
    # publish
    import re as _re
    if not _re.match(r"^[a-zA-Z0-9_.-]+\.json$", remote):
        print("invalid remote basename")
        return 2
    rc = subprocess.call([sys.executable, str(Path(__file__).parent / "publish_ci_report.py"), str(local), remote])  # nosemgrep: dangerous-subprocess-use-tainted-env-args — remote basename allowlisted
    print(f"publish_diag name={name} remote={remote} rc={rc}")
    return 0  # never fail the job solely on publish

if __name__ == "__main__":
    raise SystemExit(main())
