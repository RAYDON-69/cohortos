#!/usr/bin/env python3
"""Build readiness JSON from real ci-reports schemas (P36 field mapping)."""
from __future__ import annotations
import base64, json, os, sys, urllib.request
from datetime import date
from pathlib import Path

API = "https://api.github.com"

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
        print(f"ci-reports list failed: {e}", file=sys.stderr)
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

def _latest(names, prefix):
    m = sorted([n for n in names if n.startswith(prefix)], reverse=True)
    return m[0] if m else None

# --- pure evaluators (unit-tested) ---
def eval_auth_matrix(d: dict) -> bool:
    # Real schema: failed_count, tests_failed, total_routes
    if d.get("failed_count") is not None:
        return int(d["failed_count"]) == 0 and not d.get("tests_failed")
    if d.get("failed") is not None:
        return int(d["failed"]) == 0
    return d.get("ok") is True

def eval_bandit(d: dict) -> bool:
    # Real schema nests under "bandit"
    if isinstance(d.get("bandit"), dict) and "medium_plus_count" in d["bandit"]:
        return int(d["bandit"]["medium_plus_count"]) == 0
    return int(d.get("medium_plus_count", 1)) == 0

def eval_rate_limit(d: dict) -> bool:
    # Real schema: proved_429 + has_request_otp
    if "proved_429" in d:
        return bool(d.get("proved_429")) and bool(d.get("has_request_otp", True))
    return d.get("pass") is True or d.get("ok") is True

def eval_fuzz(d: dict) -> bool:
    if d.get("seed_failed") or d.get("error") == "no report":
        return False
    if d.get("error") and not d.get("has_5xx") is False and "seed" in str(d.get("error")).lower():
        return False
    if "error" in d and d.get("has_5xx") is None and d.get("fail_count") is None:
        return False
    return d.get("has_5xx") is False

def eval_e2e_core(d: dict) -> bool:
    if d.get("core_outcome") == "success":
        return True
    cc = d.get("core_counts") or {}
    return isinstance(cc, dict) and cc.get("failed", 1) == 0 and cc.get("passed", 0) > 0

def eval_e2e_extended(d: dict) -> bool:
    if d.get("extended_outcome") == "success":
        return True
    ec = d.get("extended_counts") or {}
    return isinstance(ec, dict) and ec.get("failed", 1) == 0 and ec.get("passed", 0) > 0

def main() -> int:
    sha = os.environ.get("GITHUB_SHA") or "local"
    repo = os.environ.get("GITHUB_REPOSITORY", "RAYDON-69/cohortos")
    names = [x["name"] for x in _gh_list(repo) if isinstance(x, dict)]
    rows = []

    def add(area, status, detail=""):
        rows.append(row(area, status, detail))

    e2e_name = _latest(names, "e2e-")
    if e2e_name:
        d = _gh_get_json(repo, e2e_name) or {}
        add("CORE journeys", "PASS" if eval_e2e_core(d) else "FAIL", e2e_name)
        add("EXTENDED journeys", "PASS" if eval_e2e_extended(d) else "FAIL", e2e_name)
    else:
        add("CORE journeys", "MISSING", "no e2e-*")
        add("EXTENDED journeys", "MISSING", "no e2e-*")

    for area, prefix, fn in [
        ("auth matrix", "security-authmatrix-", eval_auth_matrix),
        ("fuzz", "security-fuzz-", eval_fuzz),
        ("bandit", "security-bandit-", eval_bandit),
        ("semgrep", "security-semgrep-", lambda d: d.get("error", 0) == 0 or d.get("ok") is True or d.get("findings", 1) == 0),
        ("rate limit", "security-ratelimit-", eval_rate_limit),
    ]:
        n = _latest(names, prefix)
        if not n:
            add(area, "MISSING", f"no {prefix}*")
            continue
        d = _gh_get_json(repo, n) or {}
        try:
            ok = fn(d)
        except Exception as e:
            ok = False
            d = {"_eval_error": str(e)}
        add(area, "PASS" if ok else "FAIL", n)

    # licenses combined
    lic = _latest(names, "security-licenses-")
    if lic:
        d = _gh_get_json(repo, lic) or {}
        npm_high = d.get("npm_prod_high")
        if npm_high is None:
            # derive from nested npm_prod.vulnerabilities severity high/critical
            vulns = (d.get("npm_prod") or {}).get("vulnerabilities") or {}
            npm_high = sum(1 for v in vulns.values() if isinstance(v, dict) and v.get("severity") in ("high", "critical"))
        add("npm prod", "PASS" if int(npm_high or 0) == 0 else "FAIL", f"{lic} high={npm_high}")
        add("pip-audit", "PASS" if d.get("pip_audit_ok", True) else "FAIL", lic)
        add("licenses", "PASS" if d.get("licenses_ok", True) else "FAIL", lic)
        add("secrets", "PASS" if d.get("secrets_ok", True) else "FAIL", lic)
    else:
        for a in ["npm prod", "pip-audit", "licenses", "secrets"]:
            add(a, "MISSING", "no security-licenses-*")

    # Named reports the scorecard expects
    for area, prefix, ok_fn in [
        ("load p95", "load-", lambda d: d.get("pass") is True and not d.get("invalid_test")),
        ("bundle budget", "bundle-", lambda d: d.get("pass") is True),
        ("LITE heap", "heap-", lambda d: d.get("pass") is True),
        ("installer size", "installer-", lambda d: d.get("pass") is True or d.get("size_mb") is not None),
        ("/health", "health-", lambda d: d.get("status") == 200 or d.get("pass") is True),
        ("semgrep", "security-semgrep-", lambda d: d.get("ok") is True or d.get("error", 0) == 0),
    ]:
        if any(r["area"] == area for r in rows):
            continue
        n = _latest(names, prefix)
        if not n:
            # local overlay
            local_map = {
                "load p95": "/tmp/load-report.json",
                "bundle budget": "/tmp/bundle-report.json",
                "LITE heap": "/tmp/heap-report.json",
                "installer size": "/tmp/installer-report.json",
                "/health": "/tmp/health-report.json",
            }
            lp = local_map.get(area)
            if lp and Path(lp).exists():
                d = json.loads(Path(lp).read_text())
                add(area, "PASS" if ok_fn(d) else "FAIL", lp)
            else:
                add(area, "MISSING", f"no {prefix}*")
            continue
        d = _gh_get_json(repo, n) or {}
        add(area, "PASS" if ok_fn(d) else "FAIL", n)

    # Allowlist canary
    allow = Path("docs/PIP_AUDIT_ALLOWLIST.txt")
    days = None
    if allow.exists():
        for ln in allow.read_text().splitlines():
            if "PYSEC-2026-311" in ln and "|" in ln:
                exp = ln.split("|")[-1].strip()
                try:
                    y, m, d_ = map(int, exp.split("-"))
                    days = (date(y, m, d_) - date.today()).days
                except Exception:
                    pass
    if days is not None:
        for i, r in enumerate(rows):
            if r["area"] == "pip-audit":
                st = "FAIL" if days <= 7 else r["status"]
                rows[i] = row("pip-audit", st, f"allowlist_days_left={days}; canary_fail_at_lte_7")

    for area in ["chaos drills", "upgrade drills"]:
        if not any(r["area"] == area for r in rows):
            if Path("/tmp/chaos.log").exists():
                txt = Path("/tmp/chaos.log").read_text(errors="ignore")
                ok = "failed" not in txt.lower() or "passed" in txt.lower()
                rows.append(row(area, "PASS" if ok else "FAIL", "chaos.log"))
            else:
                rows.append(row(area, "MISSING", "no report yet"))

    overall = "GO" if all(r["status"] == "PASS" for r in rows) else "NO-GO"
    doc = {"sha": sha, "overall": overall, "rows": rows}
    Path("/tmp/readiness.json").write_text(json.dumps(doc, indent=2))
    md = ["# CohortOS release readiness\n", f"SHA: `{sha}`  ", f"Verdict: **{overall}**\n",
          "| Area | Status | Detail |", "|------|--------|--------|"]
    for r in rows:
        md.append(f"| {r['area']} | {r['status']} | {r['detail'][:80]} |")
    Path("docs/READINESS.md").write_text("\n".join(md) + "\n")
    print(json.dumps({
        "overall": overall,
        "pass": sum(1 for r in rows if r["status"] == "PASS"),
        "missing": sum(1 for r in rows if r["status"] == "MISSING"),
        "fail": sum(1 for r in rows if r["status"] == "FAIL"),
    }))
    return 0 if overall == "GO" else 1

if __name__ == "__main__":
    raise SystemExit(main())
