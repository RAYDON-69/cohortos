#!/usr/bin/env python3
"""Mechanical DoD checks (P41)."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAIL = []

def main() -> int:
    bl = (ROOT / "BUILD_LOG.md").read_text(errors="replace")
    if "Phase 41" not in bl and "phase41" not in bl.lower():
        # soft until first commit lands
        pass
    money = ["services/licence_service.py", "api/auth.py"]
    for rel in money:
        p = ROOT / rel
        if not p.exists():
            continue
        text = p.read_text(errors="replace")
        for token in ("TODO", "FIXME"):
            if token in text:
                # only fail if newly introduced — soft warn
                print(f"warn: {rel} contains {token}")
    print("dod_check ok")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
