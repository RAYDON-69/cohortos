#!/usr/bin/env python3
"""Poll ci-reports for gate status files for a SHA. Exit 0 only if all green."""
from __future__ import annotations
import json, os, sys, time, urllib.request, base64

API = "https://api.github.com"
REPO = os.environ.get("GITHUB_REPOSITORY", "RAYDON-69/cohortos")
REQUIRED = [
    "unit-full", "e2e-smoke", "security-gates", "readiness", "workflow-lint",
]

def list_ci_reports(token: str | None):
    url = f"{API}/repos/{REPO}/contents/ci-reports?ref=ci-reports"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "cohortos-ci-wait"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"list failed: {e}")
        return []

def get_json(name: str, token: str | None):
    url = f"{API}/repos/{REPO}/contents/ci-reports/{name}?ref=ci-reports"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "cohortos-ci-wait"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            meta = json.loads(r.read().decode())
        return json.loads(base64.b64decode(meta["content"]).decode())
    except Exception:
        return None

def main() -> int:
    sha = sys.argv[1] if len(sys.argv) > 1 else ""
    if not sha:
        print("usage: ci_wait.py <sha>")
        return 2
    short = sha[:12]
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    deadline = time.time() + int(os.environ.get("CI_WAIT_MINUTES", "30")) * 60
    print(f"waiting for gates on sha={short} required={REQUIRED}")
    last = {}
    while time.time() < deadline:
        files = list_ci_reports(token)
        names = [f.get("name", "") for f in files if isinstance(f, dict)]
        found = {}
        for g in REQUIRED:
            # status-<gate>-<sha>.json or containing sha
            matches = [n for n in names if n.startswith(f"status-{g}-") and short[:7] in n]
            if not matches:
                matches = [n for n in names if n.startswith(f"status-{g}-") and sha[:7] in n]
            if matches:
                doc = get_json(sorted(matches)[-1], token)
                if doc:
                    found[g] = doc
        # also status-<sha>.json aggregate
        agg_name = f"status-{sha}.json"
        if agg_name in names:
            last["aggregate"] = get_json(agg_name, token)
        last.update(found)
        rows = []
        for g in REQUIRED:
            d = found.get(g)
            if not d:
                rows.append((g, "MISSING", "", ""))
            else:
                rows.append((g, d.get("conclusion", "?"), ",".join(d.get("failed") or [])[:80], d.get("diag", "")))
        print("---")
        for g, st, fail, diag in rows:
            print(f"{g:16} {st:10} {fail} {diag}")
        if all(found.get(g, {}).get("conclusion") == "success" for g in REQUIRED):
            print("ALL GREEN")
            return 0
        time.sleep(30)
    print("TIMEOUT waiting for gates")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
