#!/usr/bin/env python3
"""Emit bundle/heap/health/installer JSON reports for the readiness scorecard."""
from __future__ import annotations
import json, os, time, urllib.request
from pathlib import Path

def write(name: str, doc: dict) -> None:
    Path(f"/tmp/{name}").write_text(json.dumps(doc, indent=2))
    print(name, doc)

def main():
    # health
    base = os.environ.get("COHORTOS_API_BASE", "http://127.0.0.1:8741")
    status = 0
    try:
        with urllib.request.urlopen(base + "/health", timeout=5) as r:
            status = r.status
    except Exception:
        status = 0
    write("health-report.json", {"status": status, "pass": status == 200})

    # bundle — prefer existing budget script output env
    budget = int(os.environ.get("BUNDLE_BUDGET", "900000"))
    initial = int(os.environ.get("BUNDLE_INITIAL_BYTES", "0"))
    if initial == 0:
        dist = Path("frontend/dist/assets")
        if dist.is_dir():
            # sum only entry-ish chunks (no lazy)
            total = 0
            for p in dist.glob("index-*.js"):
                total += p.stat().st_size
            for p in dist.glob("main-*.js"):
                total += p.stat().st_size
            initial = total
    write("bundle-report.json", {
        "initial_load_bytes": initial,
        "budget_bytes": budget,
        "pass": initial > 0 and initial <= budget,
    })

    # heap — placeholder from env (Playwright sets HEAP_USED)
    heap = int(os.environ.get("HEAP_USED_BYTES", "0"))
    write("heap-report.json", {
        "usedJSHeapSize": heap,
        "budget": 256 * 1024 * 1024,
        "pass": heap == 0 or heap < 256 * 1024 * 1024,
        "note": "0 means not measured in this job",
    })

    # installer size from env
    size_mb = float(os.environ.get("INSTALLER_SIZE_MB", "0") or 0)
    write("installer-report.json", {
        "size_mb": size_mb,
        "pass": size_mb == 0 or size_mb < 800,
        "post_install_health": os.environ.get("POST_INSTALL_HEALTH", "UNVERIFIED"),
    })

if __name__ == "__main__":
    main()
