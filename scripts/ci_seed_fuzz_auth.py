#!/usr/bin/env python3
"""Seed a centre-trial tenant and write access_token for schemathesis -H."""
from __future__ import annotations
import argparse, json, time, urllib.request, urllib.error

def post(url, data):
    req = urllib.request.Request(
        url, data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8741")
    ap.add_argument("--out", default="/tmp/fuzz-auth.json")
    args = ap.parse_args()
    phone = f"0171{int(time.time()) % 10**7:07d}"
    trial = post(f"{args.base}/auth/centre-trial", {
        "centre_name": f"Fuzz {int(time.time())}",
        "owner_phone": phone,
        "owner_name": "Fuzz Owner",
        "student_count": 1,
    })
    tid = trial["tenant_id"]
    otp = post(f"{args.base}/auth/request-otp", {"phone": phone, "tenant_id": tid})
    ver = post(f"{args.base}/auth/verify-otp", {
        "phone": phone, "code": otp.get("_test_code"), "otp_id": otp["otp_id"], "tenant_id": tid,
    })
    out = {"tenant_id": tid, "access_token": ver["access_token"], "phone": phone}
    open(args.out, "w").write(json.dumps(out, indent=2))
    print("seeded", tid)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
