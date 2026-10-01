#!/usr/bin/env python3
import argparse
import json
import time
import urllib.error
import urllib.request

def get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status
    except Exception as e:
        return 0

def post(url, data: bytes):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)
    except Exception:
        return 0, {}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8741")
    args = ap.parse_args()
    # Wait for API
    for i in range(30):
        if get(f"{args.base}/health") == 200:
            break
        time.sleep(1)
    else:
        raise SystemExit("API /health never became ready for rate_limit_probe")

    codes = []
    for i in range(40):
        code, headers = post(
            f"{args.base}/auth/request-otp",
            json.dumps({"phone": "01700000000"}).encode(),
        )
        codes.append(code)
    print("rate_limit_probe codes", codes[:15], "... 429_count", codes.count(429))
    if all(c == 0 for c in codes):
        raise SystemExit(f"OTP endpoint not responding: {codes[:5]}")
    if not any(c in (200, 400, 401, 422, 429) for c in codes):
        raise SystemExit(f"unexpected codes: {codes[:10]}")
    # Prefer evidence of limiter under burst
    if codes.count(429) == 0:
        print("WARNING: no 429 observed — limiter may be too loose for 40 hits")
    print("rate_limit_probe OK")

if __name__ == "__main__":
    main()
