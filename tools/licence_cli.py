#!/usr/bin/env python3
"""Founder licence tooling — private keys never written into the repo (P37 A6)."""
from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure repo root on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.licence_service import generate_keypair, sign_licence, LicenceClaims
from services.revocation import sign_revocation_list
from services.updater import UpdateManifest, sign_manifest

def cmd_keygen(args):
    out = Path(args.out_dir).expanduser().resolve()
    # Refuse writing into the git repo
    try:
        repo = ROOT.resolve()
        if str(out).startswith(str(repo)):
            print("REFUSING to write private key inside the repository", file=sys.stderr)
            return 2
    except Exception:
        pass
    out.mkdir(parents=True, exist_ok=True)
    priv, pub = generate_keypair()
    (out / "licence_private.key").write_bytes(priv)
    (out / "licence_public.key").write_bytes(pub)
    os.chmod(out / "licence_private.key", 0o600)
    print(json.dumps({"public_key_path": str(out / "licence_public.key"), "private_key_path": str(out / "licence_private.key")}))
    return 0

def _load_priv(path: str) -> bytes:
    p = Path(path).expanduser()
    if not p.exists():
        raise SystemExit(f"missing private key: {p}")
    # block repo-relative accidental paths
    if "cohortos" in str(p.resolve()) and "/tools/" in str(p.resolve()):
        raise SystemExit("refusing private key path under tools/")
    return p.read_bytes()

def cmd_issue(args):
    priv = _load_priv(args.private_key)
    exp = (datetime.now(timezone.utc) + timedelta(days=int(args.days))).isoformat()
    claims = LicenceClaims(
        tenant_id=args.tenant_id,
        plan=args.plan,
        exp=exp,
        seats=int(args.seats),
        issued_at=datetime.now(timezone.utc).isoformat(),
    )
    tok = sign_licence(priv, claims)
    print(tok)
    return 0

def cmd_sign_revocation(args):
    priv = _load_priv(args.private_key)
    ids = [x.strip() for x in args.tenants.split(",") if x.strip()]
    exp = (datetime.now(timezone.utc) + timedelta(days=int(args.days))).isoformat()
    print(sign_revocation_list(priv, ids, expires_at=exp))
    return 0

def cmd_sign_update(args):
    priv = _load_priv(args.private_key)
    m = UpdateManifest(
        version=args.version,
        url=args.url,
        sha256=args.sha256,
        min_version=args.min_version,
        released_at=datetime.now(timezone.utc).isoformat(),
    )
    print(sign_manifest(priv, m))
    return 0

def main():
    ap = argparse.ArgumentParser(prog="licence_cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen")
    k.add_argument("--out-dir", required=True, help="Directory OUTSIDE the git repo")
    k.set_defaults(func=cmd_keygen)
    i = sub.add_parser("issue-licence")
    i.add_argument("--private-key", required=True)
    i.add_argument("--tenant-id", required=True)
    i.add_argument("--plan", default="starter")
    i.add_argument("--seats", default="500")
    i.add_argument("--days", default="365")
    i.set_defaults(func=cmd_issue)
    r = sub.add_parser("sign-revocation")
    r.add_argument("--private-key", required=True)
    r.add_argument("--tenants", required=True, help="comma-separated tenant ids")
    r.add_argument("--days", default="30")
    r.set_defaults(func=cmd_sign_revocation)
    u = sub.add_parser("sign-update-manifest")
    u.add_argument("--private-key", required=True)
    u.add_argument("--version", required=True)
    u.add_argument("--url", required=True)
    u.add_argument("--sha256", required=True)
    u.add_argument("--min-version", default="1.0.0")
    u.set_defaults(func=cmd_sign_update)
    args = ap.parse_args()
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
