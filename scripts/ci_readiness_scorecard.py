#!/usr/bin/env python3
"""Build readiness JSON + docs/READINESS.md from local report files / ci-reports."""
from __future__ import annotations
import json, os, sys
from datetime import date
from pathlib import Path

def row(area, status, detail=""):
    return {"area": area, "status": status, "detail": detail}

def main():
    sha = os.environ.get("GITHUB_SHA") or "local"
    reports = {}
    for p in Path("/tmp").glob("*-report.json"):
        try:
            reports[p.stem] = json.loads(p.read_text())
        except Exception:
            pass
    # Also accept env-provided summary
    rows = []
    # Defaults MISSING until filled by CI artifacts
    areas = [
        "CORE journeys", "EXTENDED journeys", "auth matrix", "fuzz", "bandit",
        "semgrep", "npm prod", "pip-audit", "secrets", "licenses", "rate limit",
        "bundle budget", "LITE heap", "chaos drills", "upgrade drills", "load p95",
        "installer size", "/health",
    ]
    for a in areas:
        rows.append(row(a, "MISSING", "no report yet"))

    # Overlay from known files
    if Path("/tmp/load-report.json").exists():
        d = json.loads(Path("/tmp/load-report.json").read_text())
        rows = [r if r["area"] != "load p95" else row("load p95", "PASS" if d.get("pass") else "FAIL", str(d)) for r in rows]
    if Path("/tmp/bandit-report.json").exists():
        d = json.loads(Path("/tmp/bandit-report.json").read_text())
        ok = d.get("medium_plus_count", 1) == 0
        rows = [r if r["area"] != "bandit" else row("bandit", "PASS" if ok else "FAIL", str(d.get("medium_plus_count"))) for r in rows]

    # Allowlist expiry days
    allow = Path("docs/PIP_AUDIT_ALLOWLIST.txt")
    days = None
    if allow.exists():
        for ln in allow.read_text().splitlines():
            if "PYSEC-2026-311" in ln and "|" in ln:
                exp = ln.split("|")[-1].strip()
                try:
                    y, m, d = map(int, exp.split("-"))
                    days = (date(y, m, d) - date.today()).days
                except Exception:
                    pass
    if days is not None:
        st = "PASS" if days > 0 else "FAIL"
        rows = [r if r["area"] != "pip-audit" else row("pip-audit", st, f"allowlist_days_left={days}") for r in rows]

    overall = "GO" if all(r["status"] == "PASS" for r in rows) else "NO-GO"
    doc = {"sha": sha, "overall": overall, "rows": rows}
    Path("/tmp/readiness.json").write_text(json.dumps(doc, indent=2))
    md = ["# CohortOS release readiness\n", f"SHA: `{sha}`  ", f"Verdict: **{overall}**\n",
          "| Area | Status | Detail |", "|------|--------|--------|"]
    for r in rows:
        md.append(f"| {r['area']} | {r['status']} | {r['detail'][:80]} |")
    Path("docs/READINESS.md").write_text("\n".join(md) + "\n")
    print(json.dumps({"overall": overall, "pass": sum(1 for r in rows if r["status"]=="PASS"), "missing": sum(1 for r in rows if r["status"]=="MISSING")}))
    return 0 if overall == "GO" else 1

if __name__ == "__main__":
    raise SystemExit(main())
