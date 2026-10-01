#!/usr/bin/env python3
import argparse
import urllib.request

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5173/")
    args = ap.parse_args()
    with urllib.request.urlopen(args.url, timeout=10) as r:
        headers = {k.lower(): v for k, v in r.headers.items()}
        status = r.status
    print("status", status)
    # Vite dev may not send CSP — warn only for missing in dev
    for h in ("x-content-type-options", "x-frame-options", "content-security-policy"):
        print(h, headers.get(h, "MISSING"))
    print("security_headers_probe OK (dev server may omit CSP — production must set)")

if __name__ == "__main__":
    main()
