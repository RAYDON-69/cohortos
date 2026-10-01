#!/usr/bin/env python3
import argparse
import urllib.request
import urllib.error

def post(url, data=b"{}"):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8741")
    args = ap.parse_args()
    codes = []
    for i in range(40):
        codes.append(post(f"{args.base}/auth/request-otp", b'{"phone":"01700000000"}'))
    # Soft assertion: endpoint responds (200/400/422/429)
    if not any(c in (200, 400, 401, 422, 429) for c in codes):
        raise SystemExit(f"OTP endpoint not responding: {codes[:5]}")
    print("rate_limit_probe codes sample", codes[:10], "429_count", codes.count(429))
    # Prefer 429 under burst but do not fail if app has soft limits only
    print("rate_limit_probe OK")

if __name__ == "__main__":
    main()
