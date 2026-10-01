#!/usr/bin/env python3
"""Publish JSON to ci-reports via GitHub Contents API; fail if not verifiable."""
from __future__ import annotations
import base64, json, os, sys, time, urllib.error, urllib.request
API = "https://api.github.com"

def req(method, path, token, data=None):
    url = API + path
    body = None if data is None else json.dumps(data).encode()
    r = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        payload = e.read().decode()
        try: j = json.loads(payload)
        except Exception: j = {"message": payload}
        return e.code, j

def main():
    if len(sys.argv) < 3:
        print("usage: publish_ci_report.py <local.json> <remote-name.json>"); return 2
    local, remote_name = sys.argv[1], sys.argv[2]
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY") or "RAYDON-69/cohortos"
    if not token:
        print("GITHUB_TOKEN required"); return 1
    content = open(local, "rb").read()
    b64 = base64.b64encode(content).decode()
    path = f"ci-reports/{remote_name}"
    st, br = req("GET", f"/repos/{repo}/git/ref/heads/ci-reports", token)
    if st == 404:
        st2, main_ref = req("GET", f"/repos/{repo}/git/ref/heads/main", token)
        if st2 != 200:
            st2, main_ref = req("GET", f"/repos/{repo}/git/ref/heads/master", token)
        sha = main_ref.get("object", {}).get("sha")
        req("POST", f"/repos/{repo}/git/refs", token, {"ref": "refs/heads/ci-reports", "sha": sha})
    file_sha = None
    for attempt in range(5):
        st, existing = req("GET", f"/repos/{repo}/contents/{path}?ref=ci-reports", token)
        if st == 200:
            file_sha = existing.get("sha")
        payload = {"message": f"ci-report {remote_name}", "content": b64, "branch": "ci-reports"}
        if file_sha:
            payload["sha"] = file_sha
        st, res = req("PUT", f"/repos/{repo}/contents/{path}", token, payload)
        if st in (200, 201):
            break
        print(f"put attempt {attempt+1} status={st} body={str(res)[:300]}")
        time.sleep(2 ** attempt)
        file_sha = None
    else:
        print("FAILED to upload report"); return 1
    for attempt in range(5):
        st, got = req("GET", f"/repos/{repo}/contents/{path}?ref=ci-reports", token)
        if st == 200 and got.get("content"):
            print(f"VERIFIED readable: {path}"); return 0
        time.sleep(2 ** attempt)
    print("FAILED verification after upload"); return 1

if __name__ == "__main__":
    raise SystemExit(main())
