#!/usr/bin/env python3
"""Validate GitHub workflow / action YAML. Exit 1 on any error."""
from __future__ import annotations
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []

def err(path: Path, msg: str, line: int | None = None):
    loc = f"{path}:{line}" if line else str(path)
    ERRORS.append(f"{loc}: {msg}")

def load(path: Path):
    text = path.read_text(encoding="utf-8")
    try:
        return yaml.safe_load(text), text
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line = mark.line + 1 if mark else None
        err(path, f"YAML parse error: {e}", line)
        return None, text

def check_action_ref(path: Path, uses: str):
    if not isinstance(uses, str):
        return
    if uses.startswith("./.github/actions/"):
        name = uses[len("./.github/actions/"):].strip("/")
        action = ROOT / ".github" / "actions" / name / "action.yml"
        if not action.exists():
            action = ROOT / ".github" / "actions" / name / "action.yaml"
        if not action.exists():
            err(path, f"uses: {uses} — missing action.yml")

def check_workflow(path: Path, data: dict):
    if not isinstance(data, dict):
        err(path, "workflow root must be a mapping")
        return
    jobs = data.get("jobs") or {}
    if not jobs:
        err(path, "no jobs defined")
        return
    job_names = set(jobs.keys())
    for jname, job in jobs.items():
        if not isinstance(job, dict):
            err(path, f"job '{jname}' is not a mapping")
            continue
        if "runs-on" not in job and "uses" not in job:
            err(path, f"job '{jname}' missing runs-on or uses")
        needs = job.get("needs")
        if needs is not None:
            need_list = needs if isinstance(needs, list) else [needs]
            for n in need_list:
                if n not in job_names:
                    err(path, f"job '{jname}' needs nonexistent job '{n}'")
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            if "uses" in step:
                check_action_ref(path, step["uses"])
            # flag multi-line python -c with unindented look-alikes in raw text later

def main() -> int:
    paths = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    paths += sorted((ROOT / ".github" / "workflows").glob("*.yaml"))
    action_dirs = list((ROOT / ".github" / "actions").glob("*/action.yml"))
    action_dirs += list((ROOT / ".github" / "actions").glob("*/action.yaml"))

    print(f"linting {len(paths)} workflows + {len(action_dirs)} actions")
    job_summary = {}
    for path in paths:
        data, text = load(path)
        if data is None:
            continue
        check_workflow(path, data)
        jobs = list((data.get("jobs") or {}).keys())
        job_summary[path.name] = jobs
        print(f"  OK  {path.relative_to(ROOT)} jobs={jobs}" if path.name not in [e.split(':')[0] for e in ERRORS] else f"  ..  {path.relative_to(ROOT)}")
    for path in action_dirs:
        data, _ = load(path)
        if data is None:
            continue
        print(f"  OK  {path.relative_to(ROOT)}")

    if ERRORS:
        print("\nERRORS:")
        for e in ERRORS:
            print(f"  {e}")
        return 1
    print("\nAll workflows valid.")
    for name, jobs in sorted(job_summary.items()):
        print(f"  {name}: {', '.join(jobs)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
