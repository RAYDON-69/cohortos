#!/usr/bin/env python3
"""Write diag JSON for ci-reports + GITHUB_STEP_SUMMARY."""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path

def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "diag"
    api_log = Path("/tmp/api.log")
    log_tail = ""
    if api_log.exists():
        lines = api_log.read_text(errors="replace").splitlines()
        log_tail = "\n".join(lines[-300:])
    alive = False
    pid = Path("/tmp/api.pid")
    if pid.exists():
        try:
            os.kill(int(pid.read_text().strip()), 0)
            alive = True
        except Exception:
            alive = False
    py_ver = subprocess.getoutput("python --version")
    pip_list = subprocess.getoutput("pip list")[:8000]
    bandit = {}
    if Path("/tmp/bandit.json").exists():
        try:
            bandit = json.loads(Path("/tmp/bandit.json").read_text())
        except Exception as e:
            bandit = {"error": str(e)}
    st_log = ""
    if Path("/tmp/schemathesis.log").exists():
        st_log = "\n".join(Path("/tmp/schemathesis.log").read_text(errors="replace").splitlines()[-100:])
    doc = {
        "schema": "cohortos.ci-report/v1",
        "kind": "diag",
        "name": name,
        "python": py_ver,
        "api_alive": alive,
        "api_log_tail": log_tail,
        "pip_list_head": pip_list,
        "bandit_results_count": len((bandit.get("results") or [])),
        "bandit_results": (bandit.get("results") or [])[:50],
        "schemathesis_tail": st_log,
    }
    out = Path(f"/tmp/{name}.json")
    out.write_text(json.dumps(doc, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"\n## Diag {name}\n")
            f.write(f"- python: `{py_ver}`\n- api_alive: `{alive}`\n")
            f.write("```\n" + log_tail[-4000:] + "\n```\n")
    print(out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
