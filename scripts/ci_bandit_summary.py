#!/usr/bin/env python3
"""Read bandit JSON, print count + one line per finding, write summary file."""
from __future__ import annotations
import json, sys
from pathlib import Path

def summarize(bandit_path: str, summary_path: str = "/tmp/bandit_summary.txt") -> int:
    p = Path(bandit_path)
    if not p.exists():
        print("bandit json missing:", bandit_path)
        Path(summary_path).write_text("missing\n")
        return 1
    data = json.loads(p.read_text())
    results = data.get("results") or []
    print(f"count {len(results)}")
    lines = []
    for r in results:
        line = (
            f"- {r.get('filename')}:{r.get('line_number')} "
            f"{r.get('test_id')} {r.get('issue_severity')}: "
            f"{(r.get('issue_text') or '')[:100]}"
        )
        print(line)
        lines.append(
            f"{r.get('filename')}:{r.get('line_number')} {r.get('test_id')}"
        )
    Path(summary_path).write_text("\n".join(lines) + ("\n" if lines else ""))
    return 0

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/bandit.json"
    raise SystemExit(summarize(path))
