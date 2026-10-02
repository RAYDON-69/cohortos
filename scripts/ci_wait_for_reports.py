#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, sys, time, urllib.request
API = "https://api.github.com"
def _headers():
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    h = {"Accept": "application/vnd.github+json", "User-Agent": "cohortos-readiness"}
    if tok: h["Authorization"] = f"token {tok}"
    return h
def list_ci_reports(repo: str):
    url = f"{API}/repos/{repo}/contents/ci-reports?ref=ci-reports"
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        return [x["name"] for x in data if isinstance(x, dict) and "name" in x]
    except Exception as e:
        print(f"list_ci_reports error: {e}", file=sys.stderr)
        return []
REQUIRED_PREFIXES = {
    "CORE journeys": ["e2e-"], "EXTENDED journeys": ["e2e-"],
    "auth matrix": ["security-authmatrix-"], "fuzz": ["security-fuzz-"],
    "bandit": ["security-bandit-"], "semgrep": ["security-semgrep-", "security-bandit-"],
    "npm prod": ["security-licenses-"], "pip-audit": ["security-licenses-"],
    "secrets": ["security-licenses-", "security-secrets-"],
    "licenses": ["security-licenses-"], "rate limit": ["security-ratelimit-"],
}
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", required=True)
    ap.add_argument("--minutes", type=int, default=20)
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "RAYDON-69/cohortos"))
    args = ap.parse_args()
    deadline = time.time() + args.minutes * 60
    need = list(REQUIRED_PREFIXES.keys())
    found = {}
    while time.time() < deadline:
        names = list_ci_reports(args.repo)
        for area, prefixes in REQUIRED_PREFIXES.items():
            if area in found: continue
            for n in names:
                if any(n.startswith(p) for p in prefixes):
                    found[area] = n; break
        missing = [a for a in need if a not in found]
        print(json.dumps({"found": len(found), "missing": missing, "sample": names[:8]}))
        if not missing:
            Path = __import__("pathlib").Path
            Path("/tmp/ci-reports-index.json").write_text(json.dumps({"found": found, "names": names}, indent=2))
            print("all required report prefixes present"); return 0
        time.sleep(30)
    print("timeout waiting for ci-reports", file=sys.stderr)
    Path = __import__("pathlib").Path
    Path("/tmp/ci-reports-index.json").write_text(json.dumps({"found": found, "missing": [a for a in need if a not in found]}, indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
