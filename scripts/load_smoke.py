#!/usr/bin/env python3
"""Authenticated load probe — 401/403 on authorised paths count as errors."""
from __future__ import annotations
import json, os, resource, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from typing import List, Tuple

def _lock_waits():
    try:
        from services.sqlite_util import get_lock_wait_count
        return get_lock_wait_count()
    except Exception:
        return int(os.environ.get("SQLITE_LOCK_WAITS", "0") or 0)

BASE = os.environ.get("COHORTOS_API_BASE", "http://127.0.0.1:8741").rstrip("/")
TOKEN = os.environ.get("COHORTOS_LOAD_TOKEN", "")

def _req(path: str, token: str | None = None) -> Tuple[float, int]:
    t0 = time.perf_counter()
    headers = {"Accept": "application/json"}
    tok = TOKEN if token is None else token
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(BASE + path, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            code = r.status
            r.read()
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:
        code = 0
    return (time.perf_counter() - t0) * 1000, code

def _pct(lat, p):
    if not lat:
        return None
    lat = sorted(lat)
    return lat[min(len(lat) - 1, int(p / 100 * len(lat)))]

def _is_error(code: int, path: str) -> bool:
    if code == 0 or code >= 500:
        return True
    # Authorised desk paths: 401/403 are failures when we sent a token
    if TOKEN and path != "/health" and code in (401, 403):
        return True
    return False

def main() -> int:
    health_ms, health_code = _req("/health", token="")
    if health_code != 200:
        doc = {"schema": "cohortos.ci-report/v1", "kind": "load", "invalid_test": True,
               "reason": "API /health not 200", "pass": False, "error_rate": 1.0}
        open("/tmp/load-report.json", "w").write(json.dumps(doc, indent=2))
        print(json.dumps(doc, indent=2))
        return 1

    paths = ["/health", "/api/v1/students", "/api/v1/attendance", "/api/v1/fees",
             "/api/v1/dashboard", "/api/v1/batches", "/api/v1/class-sessions"]
    # Prefer tenant-scoped paths if tenant known
    tid = os.environ.get("COHORTOS_LOAD_TENANT", "")
    if tid:
        paths = ["/health", f"/t/{tid}/students", f"/t/{tid}/attendance",
                 f"/t/{tid}/batches", f"/t/{tid}/billing/usage"]

    n = int(os.environ.get("LOAD_MIX_N", "100"))
    latencies, errors, hist = [], 0, Counter()
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = [ex.submit(_req, paths[i % len(paths)]) for i in range(n)]
        for i, f in enumerate(as_completed(futs)):
            ms, code = f.result()
            path = paths[i % len(paths)]
            latencies.append(ms)
            hist[f"{path}:{code}"] += 1
            if _is_error(code, path):
                errors += 1

    # Wrong-token probe must fail the gate if it somehow gets 200
    wrong_ms, wrong_code = _req(paths[-1] if paths else "/health", token="invalid.token.value")
    wrong_token_ok = wrong_code in (401, 403, 422) or (paths[-1] == "/health")

    err_rate = errors / max(n, 1)
    invalid = err_rate > 0.05 or not wrong_token_ok
    p95 = _pct(latencies, 95)
    passed = (not invalid) and err_rate < 0.01 and (p95 or 9999) < 800
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    doc = {
        "schema": "cohortos.ci-report/v1",
        "kind": "load",
        "invalid_test": invalid,
        "n": n,
        "errors": errors,
        "error_rate": err_rate,
        "p50_ms": _pct(latencies, 50),
        "p95_ms": p95,
        "p99_ms": _pct(latencies, 99),
        "budget_p95_ms": 800,
        "per_path_status_histogram": dict(hist),
        "wrong_token_status": wrong_code,
        "wrong_token_rejected": wrong_token_ok,
        "peak_rss_mb": round(peak_rss, 1),
        "sqlite_lock_waits": _lock_waits(),
        "pass": passed,
    }
    open("/tmp/load-report.json", "w").write(json.dumps(doc, indent=2))
    print(json.dumps(doc, indent=2))
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
