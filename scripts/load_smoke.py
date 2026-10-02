#!/usr/bin/env python3
"""Real load probe: seeded API must be up; desk read mix + join burst + soak."""
from __future__ import annotations
import json, os, resource, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

BASE = os.environ.get("COHORTOS_API_BASE", "http://127.0.0.1:8741").rstrip("/")
TOKEN = os.environ.get("COHORTOS_LOAD_TOKEN", "")

def _req(path: str, method: str = "GET", body: bytes | None = None) -> Tuple[float, int]:
    t0 = time.perf_counter()
    headers = {"Accept": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            code = r.status
            r.read()
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:
        code = 0
    return (time.perf_counter() - t0) * 1000, code

def _pct(sorted_lat: List[float], p: float):
    if not sorted_lat:
        return None
    return sorted_lat[min(len(sorted_lat) - 1, int(p / 100 * len(sorted_lat)))]

def _run_mix(n: int, paths: List[str], workers: int = 20) -> dict:
    latencies, errors, codes = [], 0, []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_req, paths[i % len(paths)]) for i in range(n)]
        for f in as_completed(futs):
            ms, code = f.result()
            latencies.append(ms); codes.append(code)
            if code == 0 or code >= 500:
                errors += 1
    latencies.sort()
    return {"n": n, "errors": errors, "error_rate": errors / max(n, 1),
            "p50_ms": _pct(latencies, 50), "p95_ms": _pct(latencies, 95),
            "p99_ms": _pct(latencies, 99), "codes_sample": codes[:20]}

def main() -> int:
    health_ms, health_code = _req("/health")
    if health_code != 200:
        doc = {"invalid_test": True, "reason": "API /health not 200", "health_code": health_code,
               "health_ms": health_ms, "pass": False, "n": 0, "errors": 1, "error_rate": 1.0,
               "p50_ms": None, "p95_ms": None, "p99_ms": None, "budget_p95_ms": 800}
        print(json.dumps(doc, indent=2))
        open("/tmp/load-report.json", "w").write(json.dumps(doc, indent=2))
        return 1
    mix_paths = ["/health", "/api/v1/students", "/api/v1/attendance", "/api/v1/fees", "/api/v1/dashboard", "/api/v1/batches"]
    mix = _run_mix(int(os.environ.get("LOAD_MIX_N", "200")), mix_paths, 25)
    burst = _run_mix(int(os.environ.get("LOAD_BURST_N", "200")), ["/api/v1/class-sessions", "/health"], 40)
    soak_s = int(os.environ.get("LOAD_SOAK_S", "300"))
    soak_lat, soak_err, soak_n = [], 0, 0
    t_end = time.time() + soak_s
    while time.time() < t_end:
        ms, code = _req(mix_paths[soak_n % len(mix_paths)])
        soak_lat.append(ms); soak_n += 1
        if code == 0 or code >= 500: soak_err += 1
        time.sleep(0.25)
    soak_lat.sort()
    soak = {"n": soak_n, "errors": soak_err, "error_rate": soak_err / max(soak_n, 1),
            "p50_ms": _pct(soak_lat, 50), "p95_ms": _pct(soak_lat, 95), "p99_ms": _pct(soak_lat, 99), "duration_s": soak_s}
    peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    combined_err_rate = (mix["errors"] + burst["errors"] + soak["errors"]) / max(mix["n"] + burst["n"] + soak["n"], 1)
    p95_candidates = [x for x in [mix.get("p95_ms"), burst.get("p95_ms"), soak.get("p95_ms")] if x is not None]
    p95 = max(p95_candidates) if p95_candidates else None
    invalid = combined_err_rate > 0.05
    passed = (not invalid) and combined_err_rate < 0.01 and (p95 or 9999) < 800
    doc = {"invalid_test": invalid, "reason": "error_rate > 5%" if invalid else "",
           "mix": mix, "burst": burst, "soak": soak, "peak_rss_mb": round(peak_rss_mb, 1),
           "sqlite_lock_waits": int(os.environ.get("SQLITE_LOCK_WAITS", "0") or 0),
        "sqlite_lock_waits_note": "0 unless instrumented; peak_rss_mb measured", "n": mix["n"]+burst["n"]+soak["n"],
           "errors": mix["errors"]+burst["errors"]+soak["errors"], "error_rate": combined_err_rate,
           "p50_ms": mix.get("p50_ms"), "p95_ms": p95, "p99_ms": mix.get("p99_ms"),
           "budget_p95_ms": 800, "pass": passed}
    print(json.dumps(doc, indent=2))
    open("/tmp/load-report.json", "w").write(json.dumps(doc, indent=2))
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
