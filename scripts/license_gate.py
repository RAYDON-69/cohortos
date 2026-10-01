#!/usr/bin/env python3
"""Reject GPL/AGPL/SSPL in dependency license reports."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FORBIDDEN = re.compile(r"\b(AGPL|GPL|SSPL|CPOL)\b", re.I)


def load_allow(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    return [ln.strip() for ln in p.read_text().splitlines() if ln.strip() and not ln.startswith("#")]


def allowed(name: str, license_s: str, allow: list[str]) -> bool:
    blob = f"{name} {license_s}"
    return any(a.lower() in blob.lower() for a in allow)


def scan_pip(data, allow):
    bad = []
    if isinstance(data, list):
        for row in data:
            name = str(row.get("Name") or row.get("name") or "")
            lic = str(row.get("License") or row.get("license") or "")
            if FORBIDDEN.search(lic) and not allowed(name, lic, allow):
                bad.append(f"pip:{name}:{lic}")
    return bad


def scan_npm(data, allow):
    bad = []
    if isinstance(data, dict):
        for name, meta in data.items():
            if not isinstance(meta, dict):
                continue
            lic = str(meta.get("licenses") or meta.get("license") or "")
            if FORBIDDEN.search(lic) and not allowed(name, lic, allow):
                bad.append(f"npm:{name}:{lic}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pip-json")
    ap.add_argument("--npm-json")
    ap.add_argument("--allowlist", default="docs/LICENSE_ALLOWLIST.txt")
    ap.add_argument("--write-md")
    args = ap.parse_args()
    allow = load_allow(args.allowlist)
    bad = []
    if args.pip_json and Path(args.pip_json).exists():
        bad += scan_pip(json.loads(Path(args.pip_json).read_text() or "[]"), allow)
    if args.npm_json and Path(args.npm_json).exists():
        bad += scan_npm(json.loads(Path(args.npm_json).read_text() or "{}"), allow)
    if args.write_md:
        Path(args.write_md).write_text(
            "# Third-party licenses (generated)\n\n"
            "See CI license gate. Forbidden copyleft (GPL/AGPL/SSPL) must not ship.\n"
            f"Allowlist entries: {len(allow)}\n"
        )
    if bad:
        print("FORBIDDEN LICENSES:\n" + "\n".join(bad[:50]))
        sys.exit(1)
    print("license gate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
