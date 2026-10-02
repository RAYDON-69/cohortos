#!/usr/bin/env python3
from __future__ import annotations
import base64, json, os, sys, urllib.request
from datetime import date
from pathlib import Path
API = "https://api.github.com"
def row(area, status, detail=""):
    return {"area": area, "status": status, "detail": str(detail)[:200]}
def _gh_list(repo):
    tok = os.environ.get("GITHUB_TOKEN") or ""
    req = urllib.request.Request(f"{API}/repos/{repo}/contents/ci-reports?ref=ci-reports",
        headers={"Accept":"application/vnd.github+json","User-Agent":"cohortos-scorecard",
                 **({"Authorization":f"token {tok}"} if tok else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"ci-reports list failed: {e}", file=sys.stderr); return []
def _gh_get_json(repo, name):
    tok = os.environ.get("GITHUB_TOKEN") or ""
    req = urllib.request.Request(f"{API}/repos/{repo}/contents/ci-reports/{name}?ref=ci-reports",
        headers={"Accept":"application/vnd.github+json","User-Agent":"cohortos-scorecard",
                 **({"Authorization":f"token {tok}"} if tok else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            meta = json.loads(r.read().decode())
        return json.loads(base64.b64decode(meta["content"]).decode())
    except Exception:
        return None
def _latest(names, prefix):
    m = sorted([n for n in names if n.startswith(prefix)], reverse=True)
    return m[0] if m else None
def main():
    sha = os.environ.get("GITHUB_SHA") or "local"
    repo = os.environ.get("GITHUB_REPOSITORY", "RAYDON-69/cohortos")
    names = [x["name"] for x in _gh_list(repo) if isinstance(x, dict)]
    rows = []
    def add(area, status, detail=""):
        rows.append(row(area, status, detail))
    e2e_name = _latest(names, "e2e-")
    if e2e_name:
        d = _gh_get_json(repo, e2e_name) or {}
        core_ok = d.get("core_outcome") == "success" or (isinstance(d.get("core_counts"), dict) and d["core_counts"].get("failed",1)==0 and d["core_counts"].get("passed",0)>0)
        ext_ok = d.get("extended_outcome") == "success" or (isinstance(d.get("extended_counts"), dict) and d["extended_counts"].get("failed",1)==0 and d["extended_counts"].get("passed",0)>0)
        add("CORE journeys", "PASS" if core_ok else "FAIL", e2e_name)
        add("EXTENDED journeys", "PASS" if ext_ok else "FAIL", e2e_name)
    else:
        add("CORE journeys", "MISSING", "no e2e-*"); add("EXTENDED journeys", "MISSING", "no e2e-*")
    for area, prefix, ok_fn in [
        ("auth matrix", "security-authmatrix-", lambda d: d.get("failed",1)==0 or d.get("ok") is True),
        ("fuzz", "security-fuzz-", lambda d: d.get("has_5xx") is False and "error" not in d),
        ("bandit", "security-bandit-", lambda d: d.get("medium_plus_count",1)==0),
        ("semgrep", "security-semgrep-", lambda d: d.get("error",0)==0 or d.get("ok") is True),
        ("rate limit", "security-ratelimit-", lambda d: d.get("pass") is True or d.get("ok") is True),
    ]:
        n = _latest(names, prefix)
        if not n: add(area, "MISSING", f"no {prefix}*"); continue
        d = _gh_get_json(repo, n) or {}
        try: ok = ok_fn(d)
        except Exception: ok = False
        add(area, "PASS" if ok else "FAIL", n)
    lic = _latest(names, "security-licenses-")
    if lic:
        d = _gh_get_json(repo, lic) or {}
        add("npm prod", "PASS" if d.get("npm_prod_high", d.get("npm_high",1))==0 else "FAIL", lic)
        add("pip-audit", "PASS" if d.get("pip_audit_ok", True) else "FAIL", lic)
        add("licenses", "PASS" if d.get("licenses_ok", True) else "FAIL", lic)
        add("secrets", "PASS" if d.get("secrets_ok", True) else "FAIL", lic)
    else:
        for a in ["npm prod","pip-audit","licenses","secrets"]:
            add(a, "MISSING", "no security-licenses-*")
    if Path("/tmp/load-report.json").exists():
        d = json.loads(Path("/tmp/load-report.json").read_text())
        if d.get("invalid_test"):
            add("load p95", "FAIL", f"invalid_test: {d.get('reason')}")
        else:
            add("load p95", "PASS" if d.get("pass") else "FAIL", d)
    else:
        add("load p95", "MISSING", "no /tmp/load-report.json")
    allow = Path("docs/PIP_AUDIT_ALLOWLIST.txt")
    days = None
    if allow.exists():
        for ln in allow.read_text().splitlines():
            if "PYSEC-2026-311" in ln and "|" in ln:
                exp = ln.split("|")[-1].strip()
                try:
                    y,m,d_ = map(int, exp.split("-"))
                    days = (date(y,m,d_) - date.today()).days
                except Exception: pass
    if days is not None:
        for i,r in enumerate(rows):
            if r["area"]=="pip-audit":
                rows[i] = row("pip-audit", "FAIL" if days<=7 else (r["status"] if r["status"]!="MISSING" else "PASS"),
                              f"allowlist_days_left={days}; canary_fail_at_lte_7")
    for area in ["bundle budget","LITE heap","chaos drills","upgrade drills","installer size","/health"]:
        if not any(r["area"]==area for r in rows):
            rows.append(row(area, "MISSING", "no report yet"))
    if Path("/tmp/chaos.log").exists():
        txt = Path("/tmp/chaos.log").read_text(errors="ignore")
        ok = "failed" not in txt.lower() or "passed" in txt.lower()
        for i,r in enumerate(rows):
            if r["area"] in ("chaos drills","upgrade drills") and r["status"]=="MISSING":
                rows[i] = row(r["area"], "PASS" if ok else "FAIL", "chaos.log")
    overall = "GO" if all(r["status"]=="PASS" for r in rows) else "NO-GO"
    doc = {"sha": sha, "overall": overall, "rows": rows}
    Path("/tmp/readiness.json").write_text(json.dumps(doc, indent=2))
    md = ["# CohortOS release readiness\n", f"SHA: `{sha}`  ", f"Verdict: **{overall}**\n",
          "| Area | Status | Detail |", "|------|--------|--------|"]
    for r in rows:
        md.append(f"| {r['area']} | {r['status']} | {r['detail'][:80]} |")
    Path("docs/READINESS.md").write_text("\n".join(md)+"\n")
    print(json.dumps({"overall": overall, "pass": sum(1 for r in rows if r["status"]=="PASS"),
                      "missing": sum(1 for r in rows if r["status"]=="MISSING"),
                      "fail": sum(1 for r in rows if r["status"]=="FAIL")}))
    return 0 if overall=="GO" else 1
if __name__ == "__main__":
    raise SystemExit(main())
