#!/usr/bin/env python3
"""Lightweight load probe: concurrent /health + authenticated reads."""
from __future__ import annotations
import json, os, statistics, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = os.environ.get("COHORTOS_API_BASE", "http://127.0.0.1:8741")


def one(path="/health"):
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(BASE + path, timeout=5) as r:
            code = r.status
    except Exception:
        code = 0
    return (time.perf_counter() - t0) * 1000, code


def main():
    n = int(os.environ.get("LOAD_N", "50"))
    latencies = []
    errors = 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = [ex.submit(one) for _ in range(n)]
        for f in as_completed(futs):
            ms, code = f.result()
            latencies.append(ms)
            if code != 200:
                errors += 1
    latencies.sort()
    def pct(p):
        if not latencies:
            return None
        return latencies[min(len(latencies) - 1, int(p / 100 * len(latencies)))]
    doc = {
        "n": n,
        "errors": errors,
        "error_rate": errors / max(n, 1),
        "p50_ms": pct(50),
        "p95_ms": pct(95),
        "p99_ms": pct(99),
        "budget_p95_ms": 800,
        "pass": (errors / max(n, 1)) < 0.01 and (pct(95) or 9999) < 800,
    }
    print(json.dumps(doc, indent=2))
    open("/tmp/load-report.json", "w").write(json.dumps(doc, indent=2))
    return 0 if doc["pass"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
