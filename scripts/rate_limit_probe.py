#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, time, urllib.error, urllib.request

def get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, None
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"

def post(url, data, timeout=30.0):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), None
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), None
    except Exception as e:
        return 0, {}, f"{type(e).__name__}: {e}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8741")
    ap.add_argument("--out", default="/tmp/rate-limit-report.json")
    args = ap.parse_args()
    report = {"base": args.base, "health": [], "otp_codes": [], "errors": []}
    for i in range(60):
        code, err = get(f"{args.base}/health")
        report["health"].append({"attempt": i, "status": code, "error": err})
        if code == 200:
            break
        time.sleep(1)
    else:
        print("API /health never became ready for rate_limit_probe")
        open(args.out, "w").write(json.dumps(report, indent=2))
        raise SystemExit(1)
    try:
        with urllib.request.urlopen(f"{args.base}/openapi.json", timeout=10) as r:
            spec = json.loads(r.read().decode())
        paths = list((spec.get("paths") or {}).keys())
        report["has_request_otp"] = any("request-otp" in p for p in paths)
        print("openapi has request-otp:", report["has_request_otp"])
    except Exception as e:
        report["openapi_error"] = f"{type(e).__name__}: {e}"
    payload = json.dumps({"phone": "01700000000"}).encode()
    for i in range(40):
        code, headers, err = post(f"{args.base}/auth/request-otp", payload)
        report["otp_codes"].append({"n": i, "status": code, "error": err,
            "retry_after": headers.get("Retry-After") or headers.get("retry-after")})
        if err:
            report["errors"].append({"n": i, "error": err})
            print(f"attempt {i}: status={code} error={err}")
        else:
            print(f"attempt {i}: status={code}")
    codes = [c["status"] for c in report["otp_codes"]]
    print("codes sample", codes[:15], "429_count", codes.count(429))
    report["proved_429"] = codes.count(429) > 0
    open(args.out, "w").write(json.dumps(report, indent=2))
    if all(c == 0 for c in codes):
        raise SystemExit(f"OTP endpoint not responding: {codes[:5]} errors={report['errors'][:3]}")
    if not any(c in (200, 400, 401, 422, 429) for c in codes):
        raise SystemExit(f"unexpected codes: {codes[:10]}")
    print("rate_limit_probe OK proved_429=", report["proved_429"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
