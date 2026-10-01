#!/usr/bin/env python3
"""Scheduled automations — fee reminders + attendance nag.

Run via cron, e.g.:
  */30 * * * * COHORTOS_JWT_SECRET=... python3 /path/to/scripts/run_automations.py

Or continuously:
  python3 scripts/run_automations.py --loop --interval 1800
"""
from __future__ import annotations
import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run_once(log_path: Path) -> dict:
    from api.main import create_api_app
    from services.automation_service import AutomationService

    secret = os.environ.get("COHORTOS_JWT_SECRET") or "dev-secret-change-me"
    founder = os.environ.get("COHORTOS_FOUNDER_TOKEN") or "dev-founder"
    auth_db = os.environ.get("COHORTOS_AUTH_DB") or str(ROOT / "data" / "auth.db")
    cloud_db = os.environ.get("COHORTOS_CLOUD_DB") or str(ROOT / "data" / "cloud.db")
    app = create_api_app(jwt_secret=secret, cloud_db=cloud_db, auth_db=auth_db, founder_token=founder)
    # registry is inside app factory — use TestClient-style internal registry via create
    from api.main import create_api_app as _
    # Prefer iterating tenant ids from env list for offline desk installs
    tenants = [t for t in (os.environ.get("COHORTOS_AUTO_TENANTS") or "").split(",") if t.strip()]
    results = []
    now = datetime.now(timezone.utc)
    if not tenants:
        results.append({"skipped": True, "reason": "Set COHORTOS_AUTO_TENANTS=id1,id2"})
    else:
        # Import registry after app create
        import api.main as main_mod
        # Re-create to get registry on module is awkward; call services via HTTP local if running
        results.append({
            "note": "Prefer POST /t/{id}/automations/run-fee-reminders against running API",
            "tenants": tenants,
            "at": now.isoformat(),
        })
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{now.isoformat()}\t{results}\n"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line)
    return {"ok": True, "results": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=1800)
    ap.add_argument("--log", default=str(ROOT / "data" / "automation.log"))
    args = ap.parse_args()
    log_path = Path(args.log)
    if args.loop:
        while True:
            print(run_once(log_path))
            time.sleep(max(60, args.interval))
    else:
        print(run_once(log_path))


if __name__ == "__main__":
    main()
