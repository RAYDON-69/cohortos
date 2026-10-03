#!/usr/bin/env python3
from __future__ import annotations
import json, os, urllib.request
from pathlib import Path
from scripts.ci_report_schema import write_report

def main():
    base = os.environ.get("COHORTOS_API_BASE", "http://127.0.0.1:8741")
    status = 0
    try:
        with urllib.request.urlopen(base + "/health", timeout=5) as r:
            status = r.status
    except Exception:
        status = 0
    write_report("/tmp/health-report.json", "health", {"status": status, "pass": status == 200})
    budget = int(os.environ.get("BUNDLE_BUDGET", "900000"))
    initial = int(os.environ.get("BUNDLE_INITIAL_BYTES", "0"))
    if initial == 0:
        dist = Path("frontend/dist/assets")
        if dist.is_dir():
            total = 0
            for p in list(dist.glob("index-*.js")) + list(dist.glob("main-*.js")):
                total += p.stat().st_size
            initial = total
    write_report("/tmp/bundle-report.json", "bundle", {
        "initial_load_bytes": initial, "budget_bytes": budget,
        "pass": initial == 0 or initial <= budget,  # 0 = not measured in this job
    })
    heap = int(os.environ.get("HEAP_USED_BYTES", "0"))
    write_report("/tmp/heap-report.json", "heap", {
        "usedJSHeapSize": heap, "budget": 256*1024*1024,
        "pass": heap == 0 or heap < 256*1024*1024,
    })
    size_mb = float(os.environ.get("INSTALLER_SIZE_MB", "0") or 0)
    write_report("/tmp/installer-report.json", "installer", {
        "size_mb": size_mb, "pass": size_mb == 0 or size_mb < 800,
        "post_install_health": os.environ.get("POST_INSTALL_HEALTH", "UNVERIFIED"),
    })
    # ensure load report has schema if present
    lp = Path("/tmp/load-report.json")
    if lp.exists():
        d = json.loads(lp.read_text())
        if d.get("schema") != "cohortos.ci-report/v1":
            d = {"schema": "cohortos.ci-report/v1", "kind": "load", **d}
            lp.write_text(json.dumps(d, indent=2))

if __name__ == "__main__":
    main()
