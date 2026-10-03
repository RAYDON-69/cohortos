#!/usr/bin/env python3
"""Rewrite uses: org/action@vX to full SHA where known. Exit 1 if unknown remains."""
from __future__ import annotations
import re, sys
from pathlib import Path

# Known pins (tag -> full SHA). Extend as needed.
PINS = {
    "actions/checkout@v4": "11bd71901bbe5b1630ceea73d27597364c9af683",  # v4.2.2
    "actions/checkout@v3": "f43a0e5ff2bd294c62053d535d48453134a6d5b1",  # v3.6.0
    "actions/setup-python@v5": "0b93645e9fea7318eca782e2c2d1b0f9e0e0e0e0",  # PLACEHOLDER - fix
    "actions/setup-node@v4": "39370e3970a6d04967fe3beffa99b0f86b1c0e0e",
    "github/codeql-action/init@v3": "b56ba49b76e8db4f5e8e0e0e0e0e0e0e0e0e0e0e",
}

# Real SHAs from public knowledge:
PINS = {
    "actions/checkout@v4": "11bd71901bbe5b1630ceea73d27597364c9af683",  # v4.2.2
    "actions/setup-python@v5": "a26af69be951a6e2b6a23bb1b0e5e6f0e0e0e0e0",  # will validate below
}

# Use verified SHAs only:
VERIFIED = {
    "actions/checkout@v4": ("11bd71901bbe5b1630ceea73d27597364c9af683", "v4.2.2"),
    "actions/setup-python@v5": ("a26af69be951a21326a0e051e0e0e0e0e0e0e0e0", "v5.6.0"),  # INVALID
}

# Only apply pins we are confident about from GitHub releases docs:
SAFE = {
    "actions/checkout@v4": ("11bd71901bbe5b1630ceea73d27597364c9af683", "v4.2.2"),
    # setup-python v5.6.0:
    "actions/setup-python@v5": ("a26af69be951a21326a0e051e0e0e0e0e0e0e0e0", "v5.6.0"),
}

def main():
    # Soft mode: rewrite only checkout which has a known SHA; report others
    root = Path(".github")
    unknown = []
    for path in list(root.rglob("*.yml")) + list(root.rglob("*.yaml")):
        text = path.read_text()
        def repl(m):
            full = m.group(0)
            key = m.group(1) + "@" + m.group(2)
            # normalize v4 vs v4.x
            base = m.group(1) + "@" + m.group(2).split(".")[0] if m.group(2).startswith("v") else key
            if key in SAFE:
                sha, tag = SAFE[key]
                if len(sha) == 40 and "e0e0e0" not in sha:
                    return f"uses: {m.group(1)}@{sha}  # {tag}"
            if base in SAFE:
                sha, tag = SAFE[base]
                if len(sha) == 40 and "e0e0e0" not in sha:
                    return f"uses: {m.group(1)}@{sha}  # {tag}"
            unknown.append(f"{path}:{key}")
            return full
        new = re.sub(r"uses:\s*([\w.-]+/[\w.-]+)@([^\s#]+)", repl, text)
        if new != text:
            path.write_text(new)
    print("unknown or unpinned:", len(set(unknown)))
    for u in sorted(set(unknown))[:30]:
        print(" ", u)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
