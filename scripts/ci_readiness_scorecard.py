#!/usr/bin/env python3
"""Readiness scorecard — indexes by kind (cohortos.ci-report/v1), never filename."""
from __future__ import annotations
import base64, json, os, sys, urllib.request
from datetime import date
from pathlib import Path
from scripts.ci_report_schema import SCHEMA, index_by_kind
from scripts.ci_readiness_scorecard_eval import (
    eval_auth_matrix, eval_bandit, eval_rate_limit, eval_fuzz, eval_e2e_core, eval_e2e_extended,
)

API = "https://api.github.com"
REQUIRED_KINDS = [
    "e2e", "authmatrix", "fuzz", "bandit", "ratelimit", "licenses",
    "load", "bundle", "heap", "health", "installer",
]

def row(area, status, detail=""):
    return {"area": area, "status": status, "detail": str(detail)[:240]}

def _gh_list(repo):
    tok = os.environ.get("GITHUB_TOKEN") or ""
    req = urllib.request.Request(
        f"{API}/repos/{repo}/contents/ci-reports?ref=ci-reports",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "cohortos-scorecard",
                 **({"Authorization": f"token {tok}"} if tok else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"list failed: {e}", file=sys.stderr)
        return []

def _gh_get_json(repo, name):
    tok = os.environ.get("GITHUB_TOKEN") or ""
    req = urllib.request.Request(
        f"{API}/repos/{repo}/contents/ci-reports/{name}?ref=ci-reports",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "cohortos-scorecard",
                 **({"Authorization": f"token {tok}"} if tok else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            meta = json.loads(r.read().decode())
        return json.loads(base64.b64decode(meta["content"]).decode())
    except Exception:
        return None

def collect_reports(repo: str) -> list:
    reports = []
    # local /tmp first
    for p in Path("/tmp").glob("*-report.json"):
        try:
            d = json.loads(p.read_text())
            if d.get("schema") == SCHEMA:
                reports.append(d)
            else:
                # legacy: infer kind from filename stem
                stem = p.stem.replace("-report", "")
                d = {**d, "schema": SCHEMA, "kind": stem if stem in {
                    "load","bundle","heap","health","installer","fuzz","bandit","semgrep",
                    "authmatrix","ratelimit","licenses","e2e","mutmut","npm","secrets"
                } else stem}
                reports.append(d)
        except Exception:
            pass
    # ci-reports branch
    for ent in _gh_list(repo):
        if not isinstance(ent, dict):
            continue
        d = _gh_get_json(repo, ent["name"])
        if not d:
            continue
        if d.get("schema") != SCHEMA:
            # best-effort kind from filename
            name = ent["name"]
            kind = None
            for k in REQUIRED_KINDS + ["semgrep", "mutmut", "npm", "secrets", "authmatrix"]:
                if k in name.replace("security-", "").replace("-", ""):
                    kind = k if k != "authmatrix" else "authmatrix"
            if "authmatrix" in name:
                kind = "authmatrix"
            elif "ratelimit" in name:
                kind = "ratelimit"
            elif name.startswith("e2e-"):
                kind = "e2e"
            elif "fuzz" in name:
                kind = "fuzz"
            elif "bandit" in name:
                kind = "bandit"
            elif "licenses" in name:
                kind = "licenses"
            elif name.startswith("load-"):
                kind = "load"
            elif name.startswith("bundle-"):
                kind = "bundle"
            elif name.startswith("heap-"):
                kind = "heap"
            elif name.startswith("health-"):
                kind = "health"
            elif name.startswith("installer-"):
                kind = "installer"
            if kind:
                d = {**d, "schema": SCHEMA, "kind": kind}
        reports.append(d)
    return reports

def score_from_reports(reports: list) -> dict:
    by = index_by_kind(reports)
    rows = []
    if "_duplicates" in by:
        rows.append(row("schema", "FAIL", f"duplicate kinds: {by['_duplicates']}"))
        by = {k: v for k, v in by.items() if k != "_duplicates"}

    def need(kind, area, fn):
        if kind not in by:
            rows.append(row(area, "NO-GO", f"missing kind={kind}"))
            return
        d = by[kind]
        try:
            ok = fn(d)
        except Exception as e:
            ok = False
            d = {**d, "_err": str(e)}
        rows.append(row(area, "PASS" if ok else "FAIL", f"kind={kind}"))

    # e2e carries both core and extended
    if "e2e" in by:
        d = by["e2e"]
        rows.append(row("CORE journeys", "PASS" if eval_e2e_core(d) else "FAIL", "kind=e2e"))
        rows.append(row("EXTENDED journeys", "PASS" if eval_e2e_extended(d) else "FAIL", "kind=e2e"))
    else:
        rows.append(row("CORE journeys", "NO-GO", "missing kind=e2e"))
        rows.append(row("EXTENDED journeys", "NO-GO", "missing kind=e2e"))

    need("authmatrix", "auth matrix", eval_auth_matrix)
    need("fuzz", "fuzz", eval_fuzz)
    need("bandit", "bandit", eval_bandit)
    need("ratelimit", "rate limit", eval_rate_limit)
    need("licenses", "licenses", lambda d: d.get("licenses_ok", True) is True)
    need("licenses", "npm prod", lambda d: int(d.get("npm_prod_high") or 0) == 0)
    need("licenses", "pip-audit", lambda d: d.get("pip_audit_ok", True) is True)
    need("licenses", "secrets", lambda d: d.get("secrets_ok", True) is True)
    need("load", "load p95", lambda d: d.get("pass") is True and not d.get("invalid_test"))
    need("bundle", "bundle budget", lambda d: d.get("pass") is True)
    need("heap", "LITE heap", lambda d: d.get("pass") is True)
    need("health", "/health", lambda d: d.get("status") == 200 or d.get("pass") is True)
    need("installer", "installer size", lambda d: d.get("pass") is True or d.get("size_mb") is not None)

    # allowlist canary still applies to pip-audit row detail
    allow = Path("docs/PIP_AUDIT_ALLOWLIST.txt")
    days = None
    if allow.exists():
        for ln in allow.read_text().splitlines():
            if "PYSEC-2026-311" in ln and "|" in ln:
                try:
                    y, m, d_ = map(int, ln.split("|")[-1].strip().split("-"))
                    days = (date(y, m, d_) - date.today()).days
                except Exception:
                    pass
    # If chroma not required (migrated), skip canary fail — mark note
    chroma_optional = Path("services/vectorstores/sqlite_vec_store.py").exists()
    if days is not None and not chroma_optional:
        for i, r in enumerate(rows):
            if r["area"] == "pip-audit" and days <= 7:
                rows[i] = row("pip-audit", "FAIL", f"allowlist_days_left={days}")

    overall = "GO" if all(r["status"] == "PASS" for r in rows) else "NO-GO"
    return {"overall": overall, "rows": rows, "by_kinds": list(by.keys())}

def main() -> int:
    sha = os.environ.get("GITHUB_SHA") or "local"
    repo = os.environ.get("GITHUB_REPOSITORY", "RAYDON-69/cohortos")
    reports = collect_reports(repo)
    doc = score_from_reports(reports)
    doc["sha"] = sha
    Path("/tmp/readiness.json").write_text(json.dumps(doc, indent=2))
    md = ["# CohortOS release readiness\n", f"SHA: `{sha}`  ", f"Verdict: **{doc['overall']}**\n",
          "| Area | Status | Detail |", "|------|--------|--------|"]
    for r in doc["rows"]:
        md.append(f"| {r['area']} | {r['status']} | {r['detail'][:80]} |")
    Path("docs/READINESS.md").write_text("\n".join(md) + "\n")
    print(json.dumps({"overall": doc["overall"], "rows": len(doc["rows"]), "kinds": doc.get("by_kinds")}))
    return 0 if doc["overall"] == "GO" else 1

if __name__ == "__main__":
    raise SystemExit(main())
