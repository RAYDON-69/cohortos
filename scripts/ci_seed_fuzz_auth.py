#!/usr/bin/env python3
"""Seed a centre-trial tenant and write access_token for schemathesis -H.

ALWAYS writes --out JSON (success or failure detail) so the fuzz job can publish a report.
"""
from __future__ import annotations
import argparse, json, sys, time, urllib.request, urllib.error

def _call(method, url, data=None, timeout=30):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw[:2000]}
        return e.code, parsed, raw
    except Exception as e:
        return 0, {"error": str(e)}, str(e)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8741")
    ap.add_argument("--out", default="/tmp/fuzz-auth.json")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    report = {"ok": False, "steps": [], "access_token": "", "tenant_id": "", "error": None}

    # Health first
    st, body, raw = _call("GET", f"{base}/health")
    report["steps"].append({"step": "health", "status": st, "body": body})
    if st != 200:
        report["error"] = f"API health not 200: status={st} body={raw[:500]}"
        open(args.out, "w").write(json.dumps(report, indent=2))
        # Also write a fuzz-report so publish never sees empty
        open("/tmp/fuzz-report.json", "w").write(json.dumps({
            "error": report["error"], "has_5xx": False, "fail_count": 0, "seed_failed": True
        }, indent=2))
        print(report["error"], file=sys.stderr)
        return 1

    phone = f"0171{int(time.time()) % 10**7:07d}"
    st, trial, raw = _call("POST", f"{base}/auth/centre-trial", {
        "centre_name": f"Fuzz {int(time.time())}",
        "owner_phone": phone,
        "owner_name": "Fuzz Owner",
        "student_count": 1,
    })
    report["steps"].append({"step": "centre-trial", "status": st, "body": trial})
    if st >= 400 or not trial.get("tenant_id"):
        report["error"] = f"centre-trial failed status={st} body={raw[:800]}"
        open(args.out, "w").write(json.dumps(report, indent=2))
        open("/tmp/fuzz-report.json", "w").write(json.dumps({
            "error": report["error"], "has_5xx": st >= 500, "fail_count": 1, "seed_failed": True,
            "steps": report["steps"],
        }, indent=2))
        print(report["error"], file=sys.stderr)
        return 1
    tid = trial["tenant_id"]
    report["tenant_id"] = tid

    st, otp, raw = _call("POST", f"{base}/auth/request-otp", {"phone": phone, "tenant_id": tid})
    report["steps"].append({"step": "request-otp", "status": st, "body": {k: otp.get(k) for k in ("otp_id", "_test_code") if k in otp}})
    code = otp.get("_test_code")
    otp_id = otp.get("otp_id")
    if st >= 400 or not code or not otp_id:
        report["error"] = f"request-otp failed status={st} body={raw[:800]} (need COHORTOS_TEST_EXPOSE_OTP=1)"
        open(args.out, "w").write(json.dumps(report, indent=2))
        open("/tmp/fuzz-report.json", "w").write(json.dumps({
            "error": report["error"], "has_5xx": st >= 500, "fail_count": 1, "seed_failed": True,
            "steps": report["steps"],
        }, indent=2))
        print(report["error"], file=sys.stderr)
        return 1

    st, ver, raw = _call("POST", f"{base}/auth/verify-otp", {
        "otp_id": otp_id, "code": code, "tenant_id": tid,
    })
    report["steps"].append({"step": "verify-otp", "status": st, "body_keys": list(ver.keys()) if isinstance(ver, dict) else []})
    token = ver.get("access_token") if isinstance(ver, dict) else None
    if st >= 400 or not token:
        report["error"] = f"verify-otp failed status={st} body={raw[:800]}"
        open(args.out, "w").write(json.dumps(report, indent=2))
        open("/tmp/fuzz-report.json", "w").write(json.dumps({
            "error": report["error"], "has_5xx": st >= 500, "fail_count": 1, "seed_failed": True,
            "steps": report["steps"],
        }, indent=2))
        print(report["error"], file=sys.stderr)
        return 1

    report["ok"] = True
    report["access_token"] = token
    report["phone"] = phone
    open(args.out, "w").write(json.dumps(report, indent=2))
    print("seeded", tid)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
